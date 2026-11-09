
Projeto Bla Bla Bla

Replicar o projeto:

1. Clone o repositório em seu computador
2. Abra o diretório raíz do thermosense e insira
``` py -m  pip install pyserial```



2. Abra o arquivo em thermosense/arduino/arduino.ino
3. Selecione no botão "Board and Port" 
4. Para Board use Arduino UNO, para Port use COM3 Serial Port
    Nota: outro tipo de arduino pode ser usado, selecione a board de acordo com o arduino disponível
    Nota: se a porta COM3 não estiver disponível, use outra porta e faça as alterações no código dos arquivos na pasta thermosense/api
5. Baixe a biblioteca DHTlib por esse link: 
6. Inclua a biblioteca, selecionando na guia Skecth > Include Library > Add .ZIP Library...
7. No explador de arquivos, selecione o arquivo .zip baixado
8. Execute o arquivo arduino.ino e deixe ele rodando em segundo plano no Arduino IDE
9. Rode a aplicação