#!/bin/bash
cd "$(dirname "$0")";
python main.py >> aws_dyn_dns.log 2>&1
