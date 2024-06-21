# Start

## Setup

```bash
sudo tdnf install azure-cli dnf-utils ncurses-devel
pip install -r requirements.txt
```

```bash
# Get all the required bits for testing nano.spec
./setup.sh
```

## Run

```bash
if ! az vm list > /dev/null 2>&1; then
    az login --use-device-code
fi
export AZURE_OPENAI_ENDPOINT="https://damcilva-license-check-test.openai.azure.com/"
export CHAT_COMPLETIONS_DEPLOYMENT_NAME="test1"

# Story agent
./test1.py

# Assistant agent for nano pacakge
./assistant/assistant.py ./nano-testing/rpms/*.rpm ./nano-testing/build/SPECS/nano.spec ./nano-testing/srpms/nano-6.0-2.cm2.src.rpm

# Or for perl package (WARNING, this is SLOW!)
./assistant/assistant.py ./perl-testing/rpms/*.rpm ./perl-testing/build/SPECS/perl.spec ./perl-testing/srpms/perl-5.32.0-1.cm2.src.rpm
```

## Demo

```bash

asciinema rec demo.cast

clear

echo "" && echo "SPECS in $PWD/nano-testing/build/SPECS/:" && ls nano-testing/build/SPECS/ && \
echo "" && echo "SRPMS in $PWD/nano-testing/srpms/:" && ls nano-testing/srpms && \
echo "" && echo "RPMS in $PWD/nano-testing/rpms/:" && ls nano-testing/rpms && \
echo "" && echo "Soure Files in $PWD/nano-testing/build/BUILD/nano-6.0/:" && ls  nano-testing/build/BUILD/nano-6.0 | tail -n 7 && echo "..."


./assistant/assistant.py ./nano-testing/rpms/*.rpm ./nano-testing/build/SPECS/nano.spec ./nano-testing/srpms/nano-6.0-2.cm2.src.rpm
```
