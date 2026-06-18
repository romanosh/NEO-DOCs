$python = "C:\Users\Gabriel Orlando\AppData\Local\Programs\Python\Python311\python.exe"
$script = "C:\Users\Gabriel Orlando\OneDrive - ESTECH ESCO & ENGENHARIA LTDA\Área de Trabalho\Estech Setup NEO\app.py"

while ($true) {
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Iniciando servidor NEO..."
    & $python $script
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Servidor caiu. Reiniciando em 3 segundos..."
    Start-Sleep -Seconds 3
}
