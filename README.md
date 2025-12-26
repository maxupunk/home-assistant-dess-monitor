# DESS Monitor Cloud Home Assistant integration
## known from mobile applications as SmartESS, EnergyMate or Fronus Solar
## also known as https://www.eybond.com
## or web monitor service https://www.dessmonitor.com 

## Sobre este fork

Este repositório é um fork do projeto original do Antoxa1081, ajustado para atender minhas necessidades com um inversor **Anenji 6200 (6200W, 48V)**.

No momento, este fork **ainda não está disponível na loja/comunidade do HACS**. A instalação deve ser feita adicionando o repositório como **Custom Repository** no HACS.

## Instalação via HACS (Custom Repository)

Procedimento para HACS 2.0 ou superior:
1. Abra o painel do [HACS](https://hacs.xyz) no Home Assistant.
2. Clique nos três pontos (canto superior direito) e selecione "Custom Repositories".
3. Adicione um novo repositório customizado:
   - **Repository URL:** `https://github.com/maxupunk/home-assistant-dess-monitor`
   - **Type:** Integration
4. Clique em "Add".
5. Instale a integração.

Once installed, use Add Integration -> DESS Monitor.
Tested with devcodes:
 - 2341
 - 2376
 - 2428

**Minimum HA version 2024.11 for integration to work**

If you have problems with the setup, create an issue with information about your inverter model, datalogger devcode and diagnostic file


MQTT Standalone application client (for NodeRED integrations or other) - https://github.com/Antoxa1081/dess-monitor-mqtt

<img src="https://github.com/user-attachments/assets/9e35a387-8049-414a-b0f6-b55dc914e489" width="60%"/> 
<img src="https://github.com/user-attachments/assets/b3d86bd4-2e7f-4d81-9d47-2ce4719f1bdd" width="40%"/> 
<img src="https://github.com/user-attachments/assets/07b09a9a-f7b3-4715-82ec-f8a2ccffe70e" width="20%"/> 
<img src="https://github.com/user-attachments/assets/51cd2196-7d98-4218-8e0c-49ca13c3c1cc" width="20%"/>

