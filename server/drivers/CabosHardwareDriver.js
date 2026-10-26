/**
 * CABOS Sovereign Ecosystem - Hardware Telemetry Driver
 * Manages real-time state, sensors, and telemetry routes for Jack 🐕 and Dodo 🐈
 */

const fs = require('fs');
const path = require('path');

class CabosHardwareDriver {
  constructor() {
    this.telemetryFile = path.join(__dirname, '../vaults/local_telemetry.json');
    this.initTelemetryStore();
  }

  // Ensure local JSON storage file exists
  initTelemetryStore() {
    const dir = path.dirname(this.telemetryFile);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    if (!fs.existsSync(this.telemetryFile)) {
      const initialData = {
        jack: { battery: 95, location: "Gate patrol zone", obstacleDistCm: 140, status: "Active Ground Patrol" },
        dodo: { battery: 88, altitudeMeters: 12, mode: "Stealth Mapping", status: "Aerial Vault Recon" },
        lastUpdated: new Date().toISOString()
      };
      fs.writeFileSync(this.telemetryFile, JSON.stringify(initialData, null, 2));
    }
  }

  // Get current state of both bots
  getSystemStatus() {
    try {
      const rawData = fs.readFileSync(this.telemetryFile, 'utf8');
      return JSON.parse(rawData);
    } catch (err) {
      console.error("Error reading telemetry file:", err);
      return null;
    }
  }

  // Update telemetry stream dynamically
  updateBotTelemetry(botName, data) {
    const currentStatus = this.getSystemStatus() || {};
    if (currentStatus[botName]) {
      currentStatus[botName] = { ...currentStatus[botName], ...data };
      currentStatus.lastUpdated = new Date().toISOString();
      fs.writeFileSync(this.telemetryFile, JSON.stringify(currentStatus, null, 2));
      return { success: true, updated: currentStatus[botName] };
    }
    return { success: false, message: "Bot driver not found" };
  }
}

module.exports = CabosHardwareDriver;
