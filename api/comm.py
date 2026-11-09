import time
import serial

arduino = serial.Serial(port='COM3', baudrate=9600, timeout=2)
time.sleep(2)  # espera o Arduino reiniciar

msgWR = input('Write message to arduino: ')
arduino.write((msgWR + '\n').encode('utf-8'))

answer = arduino.readline().decode('utf-8', errors='ignore').strip()
print(f'Read message from Arduino: {answer}')

arduino.close()

