#!/bin/bash
python3 db_setup.py
mkdir -p /data
cp db/database.db /data/database.db
