const express = require('express');
const router = express.Router();

const BOTS = {
  JACK: {
    name: 'Jack',
    species: 'Dog',
    type: 'Ground Patrol & Security Driver',
    favoriteZone: 'Yard, Gate & Street',
    defaultAction: 'PATROL_GROUND_OBSTACLES'
  },
  DODO: {
    name: 'Dodo',
    species: 'Cat',
    type: 'Aerial Drone & Vault Hunter Driver',
    favoriteZone: 'Reading Room, Trees & Sky Corridor',
    defaultAction: 'STEALTH_FLIGHT_MAPPING'
  }
};

router.get('/bots/status', (req, res) => {
  res.json({
    activeDrivers: [BOTS.JACK, BOTS.DODO],
    offlineEngineReady: true,
    driveSyncStatus: 'ONLINE_OR_LOCAL_FALLBACK'
  });
});

module.exports = router;
