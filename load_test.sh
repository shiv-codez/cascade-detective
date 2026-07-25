#!/bin/bash
for i in {1..20}
do
  curl -s -X POST http://localhost:8010/order -H "Content-Type: application/json" -d '{"item": "hackathon-mug", "qty": 1}' -o /dev/null -w "Request $i: %{http_code}, %{time_total}s\n"
done