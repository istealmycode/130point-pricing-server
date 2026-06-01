# 130Point Pricing Server

A lightweight local HTTP socket server that acts as a caching and proxy layer for retrieving raw, un-slabbed card sales data. 

By keeping an authenticated browser session persistent in memory, this daemon eliminates the heavy overhead of spinning up a headless browser on every individual lookup, dropping response times from seconds down to milliseconds.

## Setup & Installation

Install the required external dependencies:
`pip install -r requirements.txt`

Make the script executable:
`chmod +x pricing_server.py`

## Usage

### 1. Start the Daemon
Run the server in a terminal window:
`./pricing_server.py`

### 2. Query the Socket
Open a second terminal window and run:
`curl -G "http://127.0.0.1:8080/search" --data-urlencode "q=1974 Dave Parker"`
