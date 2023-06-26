FROM linkedin/datahub-ingestion:head AS BUILD
USER 0

# Add the Docker repository GPG key
RUN curl -fsSL https://get.docker.com | sh && docker -v

COPY /ravendb-datahub-source /ravendb-datahub-source 
# RUN cd .. && ls
RUN pip install -e ./../ravendb-datahub-source  && \
    pip list ravendb | grep ravendb && \
    pip show datahub && \
    pip show ravendb_datahub_source
# RUN pip install ./../ravendb-datahub-source && \
#     pip show ravendb_datahub_source

# docker==6.0.1 gives the error: TypeError: load_config() got an unexpected keyword argument 'config_dict'
# --> uninstall packages before reinstalling
# https://github.com/docker/compose/issues/6339 
RUN pip uninstall docker docker-compose docker-py -y
RUN pip install docker docker-compose
RUN pip list docker | grep docker

WORKDIR /ravendb-datahub-source 
RUN export PYTHONPATH="/ravendb-datahub-source:${PYTHONPATH}" && echo $PYTHONPATH

ENTRYPOINT [ "pytest", "/ravendb-datahub-source/tests/test_ravendb.py" ]
