#!/bin/bash

GRAFANA_URL=${GRAFANA_URL:-http://localhost:3010}
DATASOURCES_PATH=${DATASOURCES_PATH:-/datasources}
DASHBOARDS_PATH=${DASHBOARDS_PATH:-/dashboards}

# Generic function to call the Vault API
grafana_api() {
  local verb=$1
  local url=$2
  local params=$3
  local bodyfile=$4
  local response
  local cmd

  cmd="curl -L -s --fail -H \"Accept: application/json\" -H \"Content-Type: application/json\" -X ${verb} -k ${GRAFANA_URL}${url} -u admin:admin"
  [[ -n "${params}" ]] && cmd="${cmd} -d \"${params}\""
  [[ -n "${bodyfile}" ]] && cmd="${cmd} --data @${bodyfile}"
  echo "Running ${cmd}"
  eval ${cmd} || return 1
  return 0
}

wait_for_api() {
  while ! grafana_api GET /api/user/preferences
  do
    sleep 5
  done
}

install_datasources() {
  local datasource

  for datasource in ${DATASOURCES_PATH}/*.json
  do
    if [[ -f "${datasource}" ]]; then
      echo "Installing datasource ${datasource}"
      if grafana_api POST /api/datasources "" "${datasource}"; then
        echo "Installed!"
      else
        echo "Installation failed"
      fi
    fi
  done
}

install_dashboards() {
  local dashboard

  for dashboard in ${DASHBOARDS_PATH}/*.json
  do
    if [[ -f "${dashboard}" ]]; then
      echo "Installing dashboard ${dashboard}"
      if grafana_api POST /api/dashboards/db "" "${dashboard}"; then
        echo "Installed!"
      else
        echo "Installation failed"
      fi
    fi
  done
}

configure_grafana() {
  wait_for_api
  install_datasources
  install_dashboards
}

echo "Running configure_grafana in the background..."
configure_grafana &
/run.sh
exit 0
