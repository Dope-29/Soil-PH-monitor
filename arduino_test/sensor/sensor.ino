#include <dummy.h>

void setup() {
  Serial.begin(115200);
}
void loop() {
  int rawValue = analogRead(34);
  // pH sensors usually output 0-5V. 
  // YOUR SENSOR: Neutral pH (7.0) reads 3.3V (at max ADC)
  float voltage = rawValue * (3.3 / 4095.0); 
  float phValue = 7 + ((3.3 - voltage) / 0.18); // Calibrated: 3.3V = pH 7

  Serial.print("Raw: "); Serial.print(rawValue);
  Serial.print(" | pH: "); Serial.println(phValue);
  delay(2000);
}