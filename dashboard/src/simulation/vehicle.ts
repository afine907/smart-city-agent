import type { Vehicle, LaneType } from '../types';
import { VEHICLE_COLORS } from '../types';

let _vehicleCounter = 0;

export function createVehicle(approach: number, lane: LaneType): Vehicle {
  _vehicleCounter++;
  return {
    id: `v_${Date.now()}_${_vehicleCounter.toString(36)}`,
    approach,
    lane,
    distance: 0,
    baseSpeed: 1.2 + Math.random() * 0.6,
    speed: 1.2 + Math.random() * 0.6,
    color: VEHICLE_COLORS[Math.floor(Math.random() * VEHICLE_COLORS.length)],
    emergency: false,
    waiting: false,
    entryTime: Date.now(),
  };
}

export function createEmergency(approach: number): Vehicle {
  _vehicleCounter++;
  return {
    id: `ev_${Date.now()}_${_vehicleCounter.toString(36)}`,
    approach,
    lane: 'through',
    distance: 0,
    baseSpeed: 2.5,
    speed: 2.5,
    color: '#ff3366',
    emergency: true,
    waiting: false,
    entryTime: Date.now(),
  };
}
