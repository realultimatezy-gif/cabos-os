const express = require('express');
const path = require('path');
const CabosHardwareDriver = require('./drivers/CabosHardwareDriver');
const GoogleDriveVaultSync = require('./vaults/googleDriveVault');

const app = express();
const PORT = process.env.PORT || 5000;

app.use(express.json());

const driver = new CabosHardwareDriver();
const vaultSync = new GoogleDriveVaultSync();

// API Route: Get live bot status & telemetry
app.get('/api/bots/status', (req, res) => {
  const telemetry = driver.getSystemStatus();
  res.json(telemetry);
});

// API Route: Update bot telemetry sensors
app.post('/api/bots/telemetry', (req, res) => {
  const { botName, sensorData } = req.body;
  const result = driver.updateBotTelemetry(botName, sensorData);
  res.json(result);
});

// API Route: Trigger cloud sync manually
app.post('/api/vault/sync', async (req, res) => {
  const result = await vaultSync.syncToDrive();
  res.json(result);
});

app.listen(PORT, () => {
  console.log(`🚀 CABOS Sovereign Core running on port ${PORT}`);
});
