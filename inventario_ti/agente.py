import requests
import wmi
import platform

# Configuração: Mude o IP para o IP do seu computador onde o app.py está rodando
URL_SERVIDOR = "http://127.0.0.1:5000/api/checkin"

def coletar_info():
    print("Coletando dados do hardware...")
    c = wmi.WMI()
    
    # Informações do Sistema
    sistema = c.Win32_ComputerSystem()[0]
    bios = c.Win32_Bios()[0]
    os = c.Win32_OperatingSystem()[0]
    proc = c.Win32_Processor()[0]

    # Tratamento simples para memória RAM (de Bytes para GB)
    ram_gb = round(int(sistema.TotalPhysicalMemory) / (1024**3), 2)

    dados = {
        "hostname": sistema.Name,
        "service_tag": bios.SerialNumber.strip(), # A Service Tag da Dell
        "modelo": sistema.Model.strip(),
        "processador": proc.Name.strip(),
        "memoria": ram_gb,
        "so": os.Caption.strip()
    }
    return dados

def enviar_dados():
    try:
        payload = coletar_info()
        print(f"Enviando dados de: {payload['hostname']}...")
        
        response = requests.post(URL_SERVIDOR, json=payload)
        
        if response.status_code == 200:
            print("Sucesso! Equipamento inventariado.")
        else:
            print(f"Erro no servidor: {response.text}")
            
    except Exception as e:
        print(f"Erro ao conectar: {e}")

if __name__ == "__main__":
    enviar_dados()