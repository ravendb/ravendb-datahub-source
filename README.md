# ravendb-datahub-source
RavenDB ingestion source for Datahub

## How to use this package
Clone this package to your machine. 

Install the pip package in your working environment (Datahub [recommends using Python environments](https://datahubproject.io/docs/cli/#using-pip)). Make sure the installation takes place in the environment where you are using the Datahub CLI to ingest metadata.

For the pip installation, use the following command from the parent directory:

```
pip install ./ravendb-datahub-source
```
You can verify the installation with the following command:
```
pip show ravendb_datahub_source     
```

Now you are able to just reference your ingestion source class as a type in the YAML recipe by using the fully qualified package name.

```
source:
  type: ravendb_datahub_source.ravendb_source.RavenDBSource
  config:
  # place for your custom config defined in the configModel
```


## How to configure a RavenDB Source

The RavenDB source has to be configured within the Ingestion Job deployed in the Business Units, within a programmatic pipeline, or in a yaml configuration file (see [Ingestion Job](#ingestion-job)).

The source recipe accepts the following attributes: 

* **connect_uri**: RavenDB connection URI.
* **database_pattern**: Regex patterns for databases to filter in ingestion (*AllowDenyPattern*, see below). Default: Allow all databases to be read.
* **collection_pattern**: Regex patterns for tables to filter in ingestion. Specify regex to match the entire collection name in allowed databases. Default: Allow all databases to be read.
* **enable_schema_inference**: Whether to infer a schema from the schemaless document database. Default: True.
* **schema_sampling_size** (Optional): Number of documents to use when inferring schema size. If set to `0`, all documents will be scanned.  Default: 1000
* **remove_metadata_from_schema**: Whether to remove @metadata field from schema. Default: True
* **max_schema_size** (Optional): Maximum number of fields to include in the schema. If the schema is downsampled, a report warning will appear and the "schema.downampled" dataset property will be "True". Default: 300
* **env**: Environment to use in namespace when constructing URNs. Default: "PROD"
* **certificate_file_path** (Optional): Path to RavenDB client certificate file
* **trust_store_file_path** (Optional): Path to trust store file




The *AllowDenyPattern* has the following structure:
``{'allow': ['.*'], 'deny': [], 'ignoreCase': True}``

For RavenDB, it would probably make sense to ignore the [\@hilo collection](https://ravendb.net/docs/article-page/5.4/csharp/studio/database/documents/documents-and-collections#the-@hilo-collection), as well as the [\@empty collection](https://ravendb.net/docs/article-page/5.4/csharp/studio/database/documents/documents-and-collections#the-@hilo-collection). For this, you can simply apply the regex pattern as found in the sample programmatic pipeline and YAML below.

Here is an **example of a programmatic pipeline** in Python:

```python
pipeline = Pipeline.create(
  {
    "run_id": "ravendb-test",
    "source": {
        "type": "ravendb_datahub_source.ravendb_source.RavenDBSource",
        "config": {
            "connect_uri": "http://localhost:8080",
            "collection_pattern":
            {
                'allow': [".*"],
                'deny': ["@.*"],
                'ignoreCase': True
            },
            "schema_sampling_size": 200,
        },
    },
    # your sink configuration
    "sink": {
      "type": "datahub-rest",
      "config": {
          "server": "http://datahub-datahub-gms.datahub.svc.cluster.local:8080"
      }
    }
  }
)

# to run the pipeline
pipeline.run()
# print the source report
pipeline.pretty_print_summary()
```

The corresponding starter **recipe in YAML format** would look like this:

```
source:
  type: ravendb_datahub_source.ravendb_source.RavenDBSource
  config:
    connect_uri: http://localhost:8080
    collection_pattern:
      allow: 
        - ".*"
      deny: 
        - "@.*"
      ignoreCase: True
    schema_sampling_size: 200

sink:
  # your sink configuration
  type: datahub-rest
  config:
    server: http://datahub-datahub-gms.datahub.svc.cluster.local:8080

```
Running this recipe is as simple as:
```
datahub ingest -c ravendb_recipe.yaml
```

**Attention:**

The default port of the DataHub GMS (Generalized Metadata Service) is ``8080`` - the same as your default RavenDB port.
If you're running both on the same machine it can cause conflicts. 
To avoid that, either
* [Change the Datahub GMS port](https://datahubproject.io/docs/cli/#environment-variables-supported) (e.g. by changing the `DATAHUB_GMS_PORT`) or
* [change the `ServerUrl` ](https://ravendb.net/docs/article-page/5.4/csharp/server/configuration/core-configuration)of your RavenDB

## How to run the tests

You have to build and run the Docker image `RavendbTest.Dockerfile` from the parent directory using the following commands:

```
docker build -f ./ravendb-datahub-source/RavendbTest.Dockerfile . -t test-ravendb
docker run -it -v /var/run/docker.sock:/var/run/docker.sock test-ravendb
```