 netsh interface portproxy add v4tov4 listenaddress=172.29.160.1 listenport=5555 connectaddress=127.0.0.1 connectport=5555
  New-NetFirewallRule -DisplayName "WSL2-ADB-Bridge" -Direction Inbound -LocalPort 5555 -Protocol TCP -Action Allow
