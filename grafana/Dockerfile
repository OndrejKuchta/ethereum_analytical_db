FROM grafana/grafana:latest

ENV GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS=vertamedia-clickhouse-datasource 

RUN apt install -y curl

COPY ./configure_grafana.sh /

ADD ./datasources /datasources
ADD ./dashboards /dashboards

ENTRYPOINT ["/configure_grafana.sh"]
