#include <dht.h>

// DEFINIÇÃO DE PINOS
const int pinSensor = 7;     // Pino do DHT22
const int pinBuzzer = 2;    // Pino do buzzer

// LIMITES PADRÃO (Alteráveis)
float maxTemperatura = 30.0;  // em ºC
float minTemperatura = 10.0;  // em ºC
float maxUmidade = 50.0;      // em %
float minUmidade = 5.0;       // em %
int intervalo = 2000;        // 2000 milisegundos

// INSTANCIAR O SENSOR E INICIALIZAR DELAY
unsigned long delayIntervalo = 100;
dht sensorDHT;

void setup() {
  // Iniciando o pino do buzzer como saída
  pinMode(pinBuzzer, OUTPUT);
  // Buzzer começa desligado
  // digitalWrite(pinBuzzer, LOW);

  // INICIANDO MONITOR SERIAL  
  Serial.begin(9600);

  // INFORMAÇÃO PARA O USUÁRIO
  Serial.println("\n");
  Serial.println("\t\t\t\t < Sistema ThermoSense >");
  Serial.println("-----------------------------------------------------------------------------------------------------");
  Serial.println("Sistema,\tTempo(mS),\tUmidade(%),\tTemperatura(C),\t\tStatus de Alerta");
  Serial.println("-----------------------------------------------------------------------------------------------------");
  delay(1000);
}

void loop() {
  // VERIFICA SE HOUVE NOVO COMANDO EXTERNO VIA SERIAL
  processarComandosSerial();

  // LEITURA DOS DADOS NO INTERVALO DEFINIDO
  if ((millis() - delayIntervalo) > intervalo) {
    unsigned long start = millis();
    int chk = sensorDHT.read22(pinSensor);
    unsigned long stop = millis();
 
    // VERIFICA SE HOUVE ERRO NA LEITURA DO DHT22
    switch (chk) {
      case DHTLIB_OK:
        Serial.print("OK,\t\t");
        break;
      case DHTLIB_ERROR_CHECKSUM:
        Serial.print("Checksum error,\t\t");
        break;
      case DHTLIB_ERROR_TIMEOUT:
        Serial.print("Time out error,\t\t");
        break;
      case DHTLIB_ERROR_CONNECT:
        Serial.print("Connect error,\t\t");
        break;
      case DHTLIB_ERROR_ACK_L:
        Serial.print("Ack Low error,\t\t");
        break;
      case DHTLIB_ERROR_ACK_H:
        Serial.print("Ack High error,\t\t");
        break;
      default:
        Serial.print("Unknown error,\t\t");
        break;
    }
 
    // EXIBINDO DADOS LIDOS NO MONITOR SERIAL
    Serial.print(stop - start);
    Serial.print(", \t\t");
    float atualUmidade = sensorDHT.humidity;
    Serial.print(atualUmidade, 1);
    Serial.print(",\t\t");
    float atualTemperatura = sensorDHT.temperature;
    Serial.print(atualTemperatura, 1);

    // LÓGICA DO ALERTA QUE ACIONA O BUZZER
    bool problema = false;

    if (sensorDHT.temperature > maxTemperatura) {
      ativarBuzzer(true);
      problema = true;
      Serial.print(",\t\t\tPERIGO (TEMPERATURA ALTA)");

    }
    if (sensorDHT.temperature < minTemperatura) {
      ativarBuzzer(true);
      problema = true;
      Serial.print(",\t\t\tPERIGO (TEMPERATURA BAIXA)");

    }
    if (sensorDHT.humidity > maxUmidade) {
      ativarBuzzer(true);
      problema = true;
      Serial.print(",\t\t\tPERIGO (UMIDADE ALTA)");
    }
    if (sensorDHT.humidity < minUmidade) {
      ativarBuzzer(true);
      problema = true;
      Serial.print(",\t\t\tPERIGO (UMIDADE BAIXA)");
    } 
    if (!problema) {
      Serial.print(",\t\t\tDentro dos limites (TUDO ESTÁ OK!)");
    }

    Serial.println();
    delayIntervalo = millis();
  }
}

// FUNCAO AUXILIAR QUE ATIVA O BUZZER
void ativarBuzzer (bool ativar) {
  if (ativar){
    tone(pinBuzzer, 2000);  //gerando uma onda quadrada (tom) de frequência 2.000Hz
    delay(intervalo/2);     //mantém o tom no Buzzer por METADE do intervalo definido                                           
    noTone(pinBuzzer);      //interrompendo o tom no pino2
  }
}

// FUNÇÃO AUXILIAR PARA RECEBER NOVOS LIMITES DE UM SOFTWARE EXTERNO
void processarComandosSerial() {
  if (Serial.available() > 0) {

    // Lê tudo o que foi enviado até a quebra de linha ('\n')
    String comandoCompleto = Serial.readStringUntil('\n');
    // Remove espaços ou quebras de linha indesejadas
    comandoCompleto.trim();
    // Procura onde está o espaço que separa o comando do valor (ex: "TMAX 30.5")
    int espacoIndex = comandoCompleto.indexOf(' ');

    if (espacoIndex > 0) {
      // Separa o texto (comando) e o número (valor)
      String comando = comandoCompleto.substring(0, espacoIndex);
      float valor = comandoCompleto.substring(espacoIndex + 1).toFloat();

      // Comparações usam ASPAS DUPLAS (" ")
      if (comando == "TMAX" || comando == "tmax") {
        maxTemperatura = valor;
        Serial.print("-> Novo limite MÁXIMO de temperatura definido para: ");
        Serial.print(maxTemperatura);
        Serial.println(" ºC");

      } else if (comando == "TMIN" || comando == "tmin") {
        minTemperatura = valor;
        Serial.print("-> Novo limite MÍNIMO de temperatura definido para: ");
        Serial.print(minTemperatura);
        Serial.println(" ºC");

      } else if (comando == "UMAX" || comando == "umax") {
        maxUmidade = valor;
        Serial.print("-> Novo limite MÁXIMO de umidade definido para: ");
        Serial.print(maxUmidade);
        Serial.println(" %");

      } else if (comando == "UMIN" || comando == "umin") {
        minUmidade = valor;
        Serial.print("-> Novo limite MÍNIMO de umidade definido para: ");
        Serial.print(minUmidade);
        Serial.println(" %");
      }
    }
  }
}