.PHONY: sim

CWD=${CURDIR}

ifeq ($(OS), Windows_NT)
VENV=.venv_windows
PYTHON=python
VENVBIN=./${VENV}/Scripts
else ifneq ("$(wildcard /.dockerenv)","")
VENV=.venv_docker
PYTHON=python3
VENVBIN=./${VENV}/bin
else
VENV=.venv_osx
PYTHON=python3
VENVBIN=./${VENV}/bin
endif

default: help 
# https://marmelab.com/blog/2016/02/29/auto-documented-makefile.html
help: ## This list of Makefile targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

sim: setup_${VENV} ## Performs coverage tests and then runs the simulator
	${VENVBIN}/${PYTHON} -m robotpy coverage sim

run: ## Runs the robot
	${VENVBIN}/${PYTHON} -m robotpy run

${VENV}:
	${PYTHON} -m venv ${VENV}

lint: ## Runs the linter(s)
	# From CI pipeline. We are more strict in our local check
	# --select=E9,F6,F7,F8,F4,W1,W2,W4,W5,W6,E11 --ignore W293
	${VENVBIN}/flake8 . --count --select=E9,F6,F7,F8,F4,W1,W2,W4,W5,W6,E11 --ignore W293,W503 --show-source --statistics --exclude */tests/pyfrc*,utils/yaml/*,.venv*/,venv*/,exclude=tests/pyfrc*,utils/yaml/*,.venv*/,venv*/,examples/robotpy

test: setup_${VENV} lint  coverage ## Does a lint and then test
	${VENVBIN}/${PYTHON} -m robotpy test

coverage: setup_${VENV} test
	${VENVBIN}/${PYTHON} -m robotpy coverage

setup_${VENV}: ${VENV}
	${VENVBIN}/${PYTHON} -m pip install --upgrade pip setuptools
	${VENVBIN}/pip install --pre -r ${CWD}/requirements.txt
	$(file > setup_${VENV})

clean:
	rm -f setup setup_${VENV}

realclean: clean
	rm -fr ${VENV}

docker: docker_build
	docker run --rm -ti -v $$(PWD):/src raptacon2022_build bash

docker_build:
	docker build . --tag raptacon2022_build

# Installs the 3rd party dependencies such as photonvision and rapatcon3200 (whatever is in the toml esp in the requires section)
# https://docs.wpilib.org/en/stable/docs/software/python/pyproject_toml.html
sync:
	${PYTHON} -m robotpy sync

deploy: sync
	${PYTHON} -m robotpy deploy

gui-exe: setup_${VENV} ## Build standalone controller config GUI executable
	${VENVBIN}/pip install pyinstaller
	${VENVBIN}/pip install -r host/requirements.txt
ifeq ($(OS), Windows_NT)
	cd host && ../${VENVBIN}/pyinstaller controller_config_win.spec --distpath ../dist --workpath ../build/gui --clean -y
else ifeq ($(shell uname),Darwin)
	cd host && ../${VENVBIN}/pyinstaller controller_config_mac.spec --distpath ../dist --workpath ../build/gui --clean -y
else
	cd host && ../${VENVBIN}/pyinstaller controller_config_linux.spec --distpath ../dist --workpath ../build/gui --clean -y
endif
	@echo "Built in: dist/"

match-monitor-exe: setup_${VENV} ## Build standalone Match Monitor executable (Windows only)
	${VENVBIN}/pip install pyinstaller
	${VENVBIN}/pip install -r host/requirements.txt
ifeq ($(OS), Windows_NT)
	${VENVBIN}/python host/make_ico.py
	cd host && ../${VENVBIN}/pyinstaller match_monitor_win.spec --distpath ../dist --workpath ../build/match_monitor --clean -y
	@echo "Built: dist/raptacon-match-monitor.exe"
else
	@echo "ERROR: Match Monitor exe is Windows-only (uses Windows tray/console APIs)"
	@exit 1
endif
