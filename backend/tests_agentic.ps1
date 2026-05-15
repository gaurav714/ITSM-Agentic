$ErrorActionPreference = 'Stop'
$sid = "agentic-" + [guid]::NewGuid().ToString().Substring(0, 8)
"=== Session: $sid ==="

# 1. Vague intent (no slow/hang/freeze keyword)
$r1 = Invoke-RestMethod -Method Post http://127.0.0.1:8000/agent/message -ContentType 'application/json' -Body (@{session_id = $sid; message = 'my workstation has been crawling for hours please help' } | ConvertTo-Json)
"`nSTEP 1 (vague intent):"
"  $($r1.message)"
"  workflow=$($r1.workflow)  state=$($r1.state)"

# 2. Natural-language device input
$r2 = Invoke-RestMethod -Method Post http://127.0.0.1:8000/agent/message -ContentType 'application/json' -Body (@{session_id = $sid; message = 'it is LAPTOP-INTUNE-01 I think' } | ConvertTo-Json)
"`nSTEP 2 (NL device):"
"  $($r2.message)"
"  state=$($r2.state)  cards=$($r2.cards.kind -join ',')"
"  --- LLM ticket draft ---"
$draft = $r2.cards | Where-Object { $_.kind -eq 'ticket_draft' } | Select-Object -First 1
if ($draft) {
    "  TITLE   : $($draft.data.title)"
    "  PRIORITY: $($draft.data.priority)"
    "  DESC    : $($draft.data.description)"
}

# 3. Natural-language confirmation
$r3 = Invoke-RestMethod -Method Post http://127.0.0.1:8000/agent/message -ContentType 'application/json' -Body (@{session_id = $sid; message = 'yes please go ahead and file it' } | ConvertTo-Json)
"`nSTEP 3 (NL confirmation):"
"  $($r3.message)"
"  state=$($r3.state)"
