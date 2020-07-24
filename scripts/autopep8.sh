#!/bin/bash

LIBFILES=""
LIBFILES="${LIBFILES} $(find ./github -name '*.py' | tr '\n' ' ')"

autopep8 -ia --ignore=E501,E402 ${LIBFILES}