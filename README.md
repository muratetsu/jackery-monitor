# Jackery API Logger

This repository provides a Python script to interact with the Jackery App API, retrieve the status of a Jackery portable power station, and log the details continuously to a CSV file.

## Prerequisites
- Python 3.x
- Required packages: `requests`, `pycryptodomex` (install via `pip install requests pycryptodomex`)

## Setup

1. Copy the sample configuration file:
   ```bash
   cp config.sample.json config.json
   ```
2. Edit `config.json` and insert your Jackery account email and password.

## Usage

Run the script to start logging:
```bash
python jackery_api.py
```

The script will:
1. Connect to the Jackery API using your credentials.
2. Continually fetch the current status (battery level, input/output wattage, temperatures, etc.) every minute.
3. Print the status to the console.
4. Append the status to `jackery_log.csv` along with a timestamp.

## Acknowledgments / Credits
The core logic for the Jackery API communication used in this project is based on the valuable work by [Hsky16](https://qiita.com/Hsky16). 
You can find the original explanation and code in their Qiita article:
[ポータブル電源 Jackery のAPIを叩いてみた](https://qiita.com/Hsky16/items/c163137265a87186ac39)

I would like to express my gratitude to the original author for generously sharing the implementation details.
