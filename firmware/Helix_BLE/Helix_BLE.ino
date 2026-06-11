/*
    Based on Neil Kolban example for IDF: https://github.com/nkolban/esp32-snippets/blob/master/cpp_utils/tests/BLE%20Tests/SampleServer.cpp
    Ported to Arduino ESP32 by Evandro Copercini
    updates by chegewara
*/

// One umbrella header replaces <BLEDevice.h> + <BLEUtils.h> + <BLEServer.h>.
#include <NimBLEDevice.h>

// See the following for generating UUIDs:
// https://www.uuidgenerator.net/

#define SERVICE_UUID        "a723b49a-2b53-46a6-a2db-02bb9e9a577c"
#define CHARACTERISTIC_UUID "61adcd67-20e9-4c38-b1d0-879445c5b732"

void setup() {
  Serial.begin(115200);
  Serial.println("Helix_BLE (NimBLE) starting...");

  NimBLEDevice::init("Guiness"); // same singleton pattern as Bluedroid's BLEDevice::init
  NimBLEServer *pServer = NimBLEDevice::createServer();
  NimBLEService *pService = pServer->createService(SERVICE_UUID);
  NimBLECharacteristic *pCharacteristic =
    pService->createCharacteristic(CHARACTERISTIC_UUID,
      NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::WRITE); // NIMBLE_PROPERTY:: enum, not BLECharacteristic::PROPERTY_*
  // NimBLEDescriptor *pDesc = pCharacteristic->createDescriptor("2901",  NIMBLE_PROPERTY::READ, 40);
  // pDesc->setValue("Helix test read/write characteristic");
  pCharacteristic->setValue("Hello from NimBLE");
  pService->start(); // NOTE: at Task 2 (adding HID) this becomes pServer->start() to bring up ALL services at once

  NimBLEAdvertising *pAdvertising = NimBLEDevice::getAdvertising();
  pAdvertising->setName("Guiness");            // 2.x no longer advertises the name by default — must set it explicitly
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->enableScanResponse(true);      // renamed from setScanResponse(); scan response is off by default in 2.x=
  NimBLEDevice::startAdvertising();

  Serial.println("Advertising as Guiness (custom service only).");
}

void loop() {
  // put your main code here, to run repeatedly:
  delay(2000);
}
