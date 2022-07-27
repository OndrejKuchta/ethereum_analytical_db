FROM grafana/grafana-oss:latest

ENV GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS=vertamedia-clickhouse-datasource 

RUN apk --no-cache add curl

COPY ./configure_grafana.sh /

ADD ./datasources /datasources
ADD ./dashboards /dashboards

ENTRYPOINT ["/configure_grafana.sh"]
