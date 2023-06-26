import json
import logging
import random
import re
import os
import ast
import numpy as np
import pytest

from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type, Union
from docker_helpers import wait_for_port, docker_compose_runner

from datahub.ingestion.run.pipeline import Pipeline
from ravendb.documents.commands.crud import PutDocumentCommand, GetDocumentsCommand
from ravendb import DocumentStore

logger = logging.getLogger()
logger.setLevel(logging.INFO)


DB_RECIPE_FILE = "ravendb_to_file_db.yml"
RAVENDB_PORT = 8080
TESTDB_NAME = "testdb"
CONTAINER_NAME = "testravendb"
CONTAINER_IP = None


# ignore timestamps and random changing values triggered by container start
IGNORE_KEYS = [
    "runId",
    "lastCollectionIndexingTime",
    "lastDatabaseEtag",
    "lastDocEtag",
    "lastObserved",
    "databaseChangeVector",
    "externalUrl",
    "sizeOnDisk",
    "tempBuffersSizeOnDisk",
    "indexes",
    "time"
]


def get_container_ip(container_name=CONTAINER_NAME):
    if CONTAINER_IP:
        return CONTAINER_IP
    else:
        import time
        import docker

        client = docker.from_env()
        print("In get_container_ip")
        try:
            print(client.containers)
            container = client.containers.get(container_name)
            ip = container.attrs["NetworkSettings"]["IPAddress"]
            logging.info(
                f"Container with name {container_name} found. IP: {ip}"
            )
            time.sleep(60)
            set_container_ip(ip)
            return ip
        except docker.errors.NotFound:
            logging.info(f"Container with name '{container_name}' not found.")
            raise docker.errors.NotFound


def set_container_ip(value):
    global CONTAINER_IP
    logging.info(f"Setting container ip to: {value}")
    CONTAINER_IP = value


@pytest.fixture(scope="module")
def test_resources_dir(pytestconfig):
    return pytestconfig.rootpath / "tests"


def is_container_running(container_name: str) -> bool:
    """Returns true if the status of the container with the given name is 'Running'"""
    import time
    import docker

    client = docker.from_env()
    
    try:
        # for c in client.containers.list(all=True):
        #     logging.info(c.name)
        container = client.containers.get(container_name)
        logging.info(
            f"Container with name {container_name} found. Status: {container.status}"
        )
        time.sleep(60)
        set_container_ip(container.attrs["NetworkSettings"]["IPAddress"])
        return container.status == "running"
    except docker.errors.NotFound:
        logging.debug(f"Container with name '{container_name}' not found.")
        return False


@pytest.fixture(scope="module")
def ravendb_runner(docker_compose_runner, pytestconfig, test_resources_dir):
    logging.info("Start RavenDB runner")
    compose_file = test_resources_dir / "docker-compose.yml"
    logging.info(compose_file)
    with docker_compose_runner(
       compose_file, "ravendb"
    ) as docker_services:
        print("hier")
        wait_for_port(
            docker_services,
            CONTAINER_NAME,
            RAVENDB_PORT,
            timeout=500,
            checker=lambda: is_container_running(CONTAINER_NAME),
        )
        yield docker_services


def load_document_store():
    logging.info(f"Loading document store of database '{TESTDB_NAME}'")
    container_ip = get_container_ip()
    store = DocumentStore(
        f"http://{container_ip}:{RAVENDB_PORT}", TESTDB_NAME
    )  # RAVEN_DATABASE)
    store.initialize()
    return store


def remove_database():
    from ravendb.serverwide.operations.common import DeleteDatabaseOperation

    logging.info("Deleting databases")
    store = load_document_store()
    store.maintenance.server.send(
        DeleteDatabaseOperation(database_name=TESTDB_NAME, hard_delete=True)
    )


def prepare_database():
    """
        Fills the database with test items, if the test items are not yet in the collections.
    """
    from ravendb.documents.indexes.definitions import IndexDefinition
    from ravendb.documents.operations.indexes import (
        GetIndexOperation,
        PutIndexesOperation,
    )

    logging.info("Preparing databases")
    store = load_document_store()
    request_executor = store.get_request_executor()

    def assert_entries_set():
        command = GetDocumentsCommand.from_single_id("testing/art1")
        request_executor.execute_command(command)
        try:
            return command.result.results[0]["@metadata"]["@id"] == "testing/art1"
        except AttributeError:
            return False

    if assert_entries_set():
        logging.info("Skipping task: Database is already prepared")
        return

    for i in range(5):
        put_command1 = PutDocumentCommand(
            key=f"testing/toy{i}",
            change_vector=None,
            document={
                "Name": f"test_toy_{i}",
                "Price": str(np.around(random.uniform(1, 100), 2)),
                "Category": "Toy",
                "Brand": "Fisher Price",
                "@metadata": {
                    "Raven-Python-Type": "Products",
                    "@collection": "Products",
                },
            },
        )
        request_executor.execute_command(put_command1)
        put_command2 = PutDocumentCommand(
            key=f"testing/art{i}",
            change_vector=None,
            document={
                "Name": f"test_art_{i}",
                "Price": str(np.around(random.uniform(1, 100), 2)),
                "Category": "Image",
                "Size": "A4",
                "Shipping": True,
                "@metadata": {
                    "Raven-Python-Type": "Products",
                    "@collection": "Products",
                },
            },
        )
        request_executor.execute_command(put_command2)
        logging.info(f"Successfull iteration {i} of inserts.")

    # create index
    index = IndexDefinition()
    index.name = "Products/Search"

    index.maps = (
        "from p in docs.Products "
        + "select new { "
        + "   Name = p.Name, "
        + "   Category = p.Category,"
        + "   Id = p.DocumentId "
        + "}"
    )
    request_executor.execute_command(
        PutIndexesOperation(index).get_command(store.conventions)
    )

    # assert entries set
    command = GetDocumentsCommand.from_single_id("testing/art1")
    request_executor.execute_command(command)
    assert assert_entries_set()
    command = GetIndexOperation(index.name).get_command(store.conventions)
    request_executor.execute_command(command)
    logging.info(command.result.__dict__)
    assert command.result != None


def run_pipeline(tmp_path):
    logging.info(f"Run database with container id {get_container_ip()}")
    # Run the metadata ingestion pipeline.
    pipeline = Pipeline.create(
        {
            "run_id": "ravendb-test",
            "source": {
                "type": "ravendb_datahub_source.metadata_ingestion.ravendb_source.RavenDBSource",
                "config": {
                    "connect_uri": f"http://{get_container_ip()}:8080",
                    "collection_pattern":
                    {
                        'allow': [".*"],
                        'deny': ["@.*"],
                        'ignoreCase': True
                    },
                    "schema_sampling_size": 200,
                },
            },
            "sink": {
                "type": "file",
                "config": {
                    "filename": f"{tmp_path}/ravendb_mces.json"
                },
            },
        }
    )
    pipeline.run()
    pipeline.raise_from_status()
    pipeline.pretty_print_summary()


def test_ravendb_ingest_without_collections(
    ravendb_runner, test_resources_dir, tmp_path, pytestconfig
):
    run_pipeline(tmp_path)

    golden_path = test_resources_dir / "ravendb_mces_no_collections_golden.json"
    output_path = tmp_path / "ravendb_mces.json"
    check_golden_file(output_path, golden_path, pytestconfig)


def test_ravendb_ingest_with_db(
    ravendb_runner, test_resources_dir, tmp_path, pytestconfig
):
    # Set up database
    prepare_database()
    run_pipeline(tmp_path)

    golden_path = test_resources_dir / "ravendb_mces_with_db_golden.json"
    output_path = tmp_path / "ravendb_mces.json"
    check_golden_file(output_path, golden_path, pytestconfig)


def test_ravendb_ingest_without_documentstore(
    ravendb_runner, test_resources_dir, tmp_path, pytestconfig
):
    remove_database()
    run_pipeline(tmp_path)

    golden_path = test_resources_dir / "ravendb_mces_no_documentstore_golden.json"
    output_path = tmp_path / "ravendb_mces.json"
    check_golden_file(output_path, golden_path, pytestconfig)


def check_golden_file(output_file_path, golden_file_path, pytestconfig):
    """
    Check mce output file against golden file ignoring the keys in IGNORE_KEYS array
    since they are run dependent.
    Also verifying the database indexes are equal - ignoring the lastIndexTime.
    """

    def find_key_chains(d, target_key, current_chain=None, key_chains=None):
        if current_chain is None:
            current_chain = []
        if key_chains is None:
            key_chains = []

        if isinstance(d, dict):
            for k, v in d.items():
                if k == target_key:
                    key_chains.append(current_chain + [k])
                find_key_chains(v, target_key, current_chain + [k], key_chains)
        elif isinstance(d, list):
            for i, v in enumerate(d):
                find_key_chains(v, target_key, current_chain + [i], key_chains)

        return key_chains

    def construct_key_regex(keys_list, escape=True):
        regex_list = []

        for keys in keys_list:
            s = "root[XX]"
            for key in keys:
                if isinstance(key, int):
                    replace = f"[{str(key)}][XX]"
                else:
                    replace = f"['{str(key)}'][XX]"
                s = s.replace("[XX]", replace)
            s = s.replace("[XX]", "")
            if escape:
                regex_string = re.escape(s)
                regex_string = re.sub(r"\d+", r"\\d+", regex_string)
                # print(regex_string)
                regex_list.append(regex_string)
            else:
                regex_list.append(s)
        return list(set(regex_list))

    def compare_strings(string1, string2):
        '''
        Function to compare strings of indexes array while ignoring "lastIndexingTime" attribute
        '''
        # Parse strings into lists of dictionaries
        list1 = ast.literal_eval(string1)
        list2 = ast.literal_eval(string2)

        def remove_key_case_insensitive(dictionary, key):
            # Perform a case-insensitive search for the key
            lowercase_key = key.lower()
            for k in list(dictionary.keys()):
                if k.lower() == lowercase_key:
                    del dictionary[k]

        # Remove "lastIndexingTime" key from dictionaries
        for item in list1:
            remove_key_case_insensitive(item, "LastIndexingTime")
        for item in list2:
            remove_key_case_insensitive(item, "LastIndexingTime")

        # Compare the modified lists
        return list1 == list2

    with open(str(golden_file_path), "r") as f:
        golden = json.load(f)

    ignore_paths = []
    for key in IGNORE_KEYS:
        keys = find_key_chains(golden, key)
        ignore_paths.extend(construct_key_regex(keys))

    # ignore timestamps and random changing values triggered by container start
    # correct key structure extracted from golden file

    # replace timestamps of string of indexes list
    indexes_key_out = find_key_chains(golden, "indexes")
    indexes_out = construct_key_regex(indexes_key_out, escape=False)

    with open(str(output_file_path), "r") as f:
        output = json.load(f)

    # list of indexes
    for i in indexes_out:
        i_output = eval(i.replace("root", "output").replace("\'", "\""))
        i_golden = eval(i.replace("root", "golden").replace("\'", "\""))
        assert compare_strings(
            i_output, i_golden), f"Indexes ({indexes_out}) are different:\nOutput: {str(i_output)}\nGolden: {str(i_golden)}"
    logging.info(
        "Indexes are equal: Removing indexes from golden file check.")
    ignore_paths.extend(construct_key_regex(indexes_key_out))
    logging.info("Ignoring attributes during check:")
    [print(key) for key in ignore_paths]

    # Verify the output.
    assert_mces_equal(
        output_path=output_file_path,
        golden_path=golden_file_path,
        ignore_paths=ignore_paths,
    )


def load_json_file(filename: Union[str, os.PathLike]) -> object:
    with open(str(filename)) as f:
        a = json.load(f)
    return a


def assert_mces_equal(
    output_path: Union[str, os.PathLike],
    golden_path: Union[str, os.PathLike], ignore_paths: Optional[List[str]] = None
) -> None:

    output = load_json_file(output_path)
    golden = load_json_file(output_path)

    # This method assumes we're given a list of MCE json objects.
    diff = deepdiff.DeepDiff(
        golden, output, exclude_regex_paths=ignore_paths, ignore_order=True
    )
    if diff:
        # Attempt a clean diff (removing None-s)
        assert isinstance(output, list)
        assert isinstance(golden, list)
        clean_output = [clean_nones(o) for o in output]
        clean_golden = [clean_nones(g) for g in golden]
        clean_diff = deepdiff.DeepDiff(
            clean_golden,
            clean_output,
            exclude_regex_paths=ignore_paths,
            ignore_order=True,
        )
        if not clean_diff:
            logger.debug(
                f"MCE-s differ, clean MCE-s are fine\n{pprint.pformat(diff)}")
        diff = clean_diff
        if diff:
            # do some additional processing to emit helpful messages
            output_urns = _get_entity_urns(output)
            golden_urns = _get_entity_urns(golden)
            in_golden_but_not_in_output = golden_urns - output_urns
            in_output_but_not_in_golden = output_urns - golden_urns
            if in_golden_but_not_in_output:
                logger.info(
                    f"Golden file has {len(in_golden_but_not_in_output)} more urns: {in_golden_but_not_in_output}"
                )
            if in_output_but_not_in_golden:
                logger.info(
                    f"Golden file has {len(in_output_but_not_in_golden)} more urns: {in_output_but_not_in_golden}"
                )

    assert (
        not diff
    ), f"MCEs differ\n{pprint.pformat(diff)} \n output was: {json.dumps(output)}"
