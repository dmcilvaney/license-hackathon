# Start

## Setup

```bash
sudo tdnf install azure-cli dnf-utils
pip install -r requirements.txt
```

```bash
# Get all the requipred bits for testing nano.spec
./setup.sh
```

## Run

```bash
if ! az account show > /dev/null 2>&1; then
    az login --use-device-code
fi
export AZURE_OPENAI_ENDPOINT="https://damcilva-license-check-test.openai.azure.com/"
export CHAT_COMPLETIONS_DEPLOYMENT_NAME="test1"
./test1.py
```
