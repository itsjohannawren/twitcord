#!/usr/bin/env bash

__DIR__="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd -P 2>/dev/null)"
if [ -z "${__DIR__}" ]; then
	echo "Error: Failed to determine directory containing this script" 1>&2
	exit 1
else
	#shellcheck disable=SC2034
	__FILE__="${__DIR__}/$(basename "${BASH_SOURCE[0]}")"
fi

if [ ! -e "${__DIR__}/history.json" ]; then
	echo "{}" > "${__DIR__}/history.json"
fi

if [ ! -e "${__DIR__}/state.json" ]; then
	echo "{}" > "${__DIR__}/state.json"
fi

if [ ! -e "${__DIR__}/config.yaml" ]; then
	echo "Error: Missing config.yaml" 1>&2
	exit 1
fi

exec docker run \
	-i \
	--rm \
	-v "${__DIR__}/config.yaml:/app/config.yaml:ro" \
	-v "${__DIR__}/state.json:/app/state.json" \
	-v "${__DIR__}/history.json:/app/history.json" \
	twitcord:dev
