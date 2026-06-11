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

  // ---- BLE pairing/security config -------------------------------------------------
  // Both calls are static NimBLEDevice setters that write fields in NimBLE's global host
  // security config (ble_hs_cfg). They MUST come after init(): init() zeroes these fields
  // (NimBLEDevice.cpp:992-995), so setting them earlier would be wiped.
  //
  // WHY this exists: the security-less skeleton stored no Long-Term Key (LTK), so when a
  // bonded Windows central auto-initiated encryption on reconnect the board rejected it
  // (0x06 "PIN or Key Missing") and Windows killed the link (ISSUES.md #3). Also mandatory
  // for Task 2: the HID input report is READ_ENC (NimBLEHIDDevice.cpp:181) -> no encrypted
  // link, no keystroke subscription.
  //
  // setSecurityAuth(bool bonding, bool mitm, bool sc) sets ble_hs_cfg.sm_bonding/sm_mitm/
  // sm_sc (NimBLEDevice.cpp:1179-1183). Args here = (true, false, true):
  //   bonding = true  -> store the LTK persistently in NVS (bond data; survives reboot/RST
  //                      because CONFIG_BT_NIMBLE_NVS_PERSIST = 1, nimconfig.h:277), so a
  //                      bonded central's reconnect re-encryption finds a matching key.
  //                      Default is 0 (NimBLEDevice.cpp:993) -> exactly the skeleton's bug.
  //   mitm    = false -> do NOT request Man-In-The-Middle protection. MITM needs an
  //                      authenticated method (passkey / numeric compare), which needs I/O
  //                      hardware this board lacks; requesting it would be a no-op the link
  //                      can't honor. Result: an unauthenticated bond.
  //   sc      = true  -> use LE Secure Connections (Bluetooth 4.2 ECDH pairing) instead of
  //                      legacy pairing (NimBLEDevice.cpp:1177). Needs no I/O -> safe to enable.
  NimBLEDevice::setSecurityAuth(true, false, true);
  //
  // setSecurityIOCap(uint8_t iocap) sets ble_hs_cfg.sm_io_cap (NimBLEDevice.cpp:1210-1211).
  // NO_INPUT_OUTPUT (0x03, "NoInputNoOutput", NimBLEDevice.cpp:1207) declares no display and
  // no keypad. The pairing method is chosen from BOTH peers' I/O capabilities; when one side
  // has no I/O the only available method is Just Works -> pairing completes with no passkey
  // or numeric-comparison UI. Right for a headless ESP32 (silent bond with Windows); the
  // trade-off is no MITM protection (hence mitm = false above).
  NimBLEDevice::setSecurityIOCap(BLE_HS_IO_NO_INPUT_OUTPUT);
  // ----------------------------------------------------------------------------------

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
  Serial.println("Bonding enabled (Just Works) — re-pair Guiness in Windows after flashing.");
}

void loop() {
  // put your main code here, to run repeatedly:
  delay(2000);
}
