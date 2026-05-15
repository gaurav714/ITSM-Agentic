$ErrorActionPreference = 'Stop'
$sid = "fresh-" + [guid]::NewGuid().ToString().Substring(0,8)
"Using session: $sid"
Invoke-RestMethod -Method Post http://127.0.0.1:8000/diagnostics/browser -ContentType 'application/json' -Body (@{session_id=$sid; user_agent='TestUA'; cpu_cores=8; device_memory_gb=16; online=$true; page_load_ms=1234} | ConvertTo-Json) | Out-Null
$a = Invoke-RestMethod -Method Post http://127.0.0.1:8000/agent/message -ContentType 'application/json' -Body (@{session_id=$sid; message='My laptop is hanging'} | ConvertTo-Json)
"A: $($a.message)  [state=$($a.state)]"
$b = Invoke-RestMethod -Method Post http://127.0.0.1:8000/agent/message -ContentType 'application/json' -Body (@{session_id=$sid; message='UNKNOWN-PC'} | ConvertTo-Json)
"B: $($b.message)"
"  state=$($b.state)  trigger=$($b.metadata.trigger_browser_diagnostics)  cards=$($b.cards.kind -join ',')"
$c = Invoke-RestMethod -Method Post http://127.0.0.1:8000/agent/message -ContentType 'application/json' -Body (@{session_id=$sid; message='browser ready'} | ConvertTo-Json)
"C: $($c.message.Substring(0,[Math]::Min(200,$c.message.Length)))"
"  state=$($c.state)  cards=$($c.cards.kind -join ',')"
$d = Invoke-RestMethod -Method Post http://127.0.0.1:8000/agent/message -ContentType 'application/json' -Body (@{session_id=$sid; message='yes'} | ConvertTo-Json)
"D: $($d.message)  [state=$($d.state)]"
