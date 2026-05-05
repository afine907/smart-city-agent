import type { Vehicle, Position } from '../types';
import { roundedRect } from './helpers';

export function drawVehicle(
  ctx: CanvasRenderingContext2D,
  vehicle: Vehicle,
  pos: Position,
): void {
  ctx.save();
  ctx.translate(pos.x, pos.y);
  ctx.rotate(pos.angle);

  if (vehicle.emergency) {
    drawEmergencyVehicle(ctx, vehicle);
  } else {
    drawNormalVehicle(ctx, vehicle);
  }

  ctx.restore();
}

function drawEmergencyVehicle(ctx: CanvasRenderingContext2D, _v: Vehicle): void {
  const pulse = Math.sin(Date.now() / 120) * 0.4 + 0.6;
  ctx.shadowColor = '#ff3366';
  ctx.shadowBlur = 20 * pulse;
  ctx.fillStyle = '#ff3366';
  roundedRect(ctx, -14, -7, 28, 14, 4);
  ctx.fill();

  // Windshield
  ctx.fillStyle = '#991133';
  ctx.fillRect(4, -5, 5, 10);

  // Siren lights
  const sirenPhase = Math.floor(Date.now() / 150) % 2;
  ctx.shadowBlur = 10;
  ctx.shadowColor = sirenPhase ? '#4488ff' : '#ff3366';
  ctx.fillStyle = sirenPhase ? '#4488ff' : '#ff3366';
  ctx.beginPath(); ctx.arc(-8, -8, 4, 0, Math.PI * 2); ctx.fill();
  ctx.shadowColor = sirenPhase ? '#ff3366' : '#4488ff';
  ctx.fillStyle = sirenPhase ? '#ff3366' : '#4488ff';
  ctx.beginPath(); ctx.arc(8, -8, 4, 0, Math.PI * 2); ctx.fill();
  ctx.shadowBlur = 0;
}

function drawNormalVehicle(ctx: CanvasRenderingContext2D, v: Vehicle): void {
  const vw = v.waiting ? 18 : 22;
  const vh = v.waiting ? 10 : 12;
  const hw = vw / 2;
  const hh = vh / 2;

  // Shadow
  ctx.shadowColor = v.color;
  ctx.shadowBlur = v.waiting ? 4 : 10;

  // Body
  ctx.fillStyle = v.color;
  roundedRect(ctx, -hw, -hh, vw, vh, 3);
  ctx.fill();

  // Windshield
  ctx.fillStyle = 'rgba(0,0,0,0.35)';
  ctx.fillRect(hw - 7, -hh + 2, 5, vh - 4);

  // Rear window
  ctx.fillStyle = 'rgba(0,0,0,0.25)';
  ctx.fillRect(-hw + 2, -hh + 2, 4, vh - 4);
  ctx.shadowBlur = 0;

  // Headlights
  ctx.fillStyle = '#fff';
  ctx.shadowColor = '#fff';
  ctx.shadowBlur = 4;
  ctx.fillRect(hw - 2, -hh + 1, 2, 2.5);
  ctx.fillRect(hw - 2, hh - 3.5, 2, 2.5);
  ctx.shadowBlur = 0;

  // Taillights
  ctx.fillStyle = '#ff4444';
  ctx.shadowColor = '#ff4444';
  ctx.shadowBlur = v.waiting ? 6 : 2;
  ctx.fillRect(-hw, -hh + 1, 2, 2.5);
  ctx.fillRect(-hw, hh - 3.5, 2, 2.5);
  ctx.shadowBlur = 0;
}
