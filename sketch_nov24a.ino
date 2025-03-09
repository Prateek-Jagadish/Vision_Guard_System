const int ledPin = 9;  // LED connected to pin 9

void setup() {
  pinMode(ledPin, OUTPUT);
  analogWrite(ledPin, 255);  // Start at full brightness
  Serial.begin(9600);
  // Blink once to show it's working
  digitalWrite(ledPin, LOW);
  delay(500);
  digitalWrite(ledPin, HIGH);
}

void loop() {
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    
    if (command == "DIM") {
      analogWrite(ledPin, 128);  // 50% brightness
      Serial.println("OK");
    } 
    else if (command == "RESET") {
      analogWrite(ledPin, 255);  // Full brightness
      Serial.println("OK");
    }
    else if (command == "TEST") {
      Serial.println("OK");
    }
  }
}