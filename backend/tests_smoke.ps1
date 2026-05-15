$ErrorActionPreference = 'Stop'
Invoke-RestMethod -Method Post http://127.0.0.1:8000/diagnostics/browser -ContentType 'application/json' -Body '{"session_id":"s4","user_agent":"TestUA","cpu_cores":8,"device_memory_gb":16,"online":true,"page_load_ms":1234}' | Out-Null
$a = Invoke-RestMethod -Method Post http://127.0.0.1:8000/agent/message -ContentType 'application/json' -Body '{"session_id":"s4","message":"My laptop is hanging"}'
"A: $($a.message)"
$b = Invoke-RestMethod -Method Post http://127.0.0.1:8000/agent/message -ContentType 'application/json' -Body '{"session_id":"s4","message":"UNKNOWN-PC"}'
"B: $($b.message)"
"  state=$($b.state)  trigger=$($b.metadata.trigger_browser_diagnostics)"
$c = Invoke-RestMethod -Method Post http://127.0.0.1:8000/agent/message -ContentType 'application/json' -Body '{"session_id":"s4","message":"browser ready"}'
"C: $($c.message)"
"  state=$($c.state)  cards=" + ($c.cards.kind -join ',')

# Start-workflow path
$d = Invoke-RestMethod -Method Post http://127.0.0.1:8000/agent/start_workflow -ContentType 'application/json' -Body '{"session_id":"s5","workflow_id":"password_reset"}'
"D (placeholder): $($d.message)"
