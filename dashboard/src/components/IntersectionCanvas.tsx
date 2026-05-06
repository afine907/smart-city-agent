import { useRef, useEffect, useCallback } from 'react';
import type { Scenario } from '../simulation/engine';
import { SimulationEngine } from '../simulation/engine';
import type { SignalController } from '../simulation/controller';
import { getPositionOnPath } from '../rendering/helpers';
import { drawBackground } from '../rendering/roads';
import { drawCrossroad, drawTJunction, drawRoundabout, drawXIntersection, drawStraightRoad } from '../rendering/roads';
import { drawCrossroadMarkings, drawTJunctionMarkings, drawRoundaboutMarkings, drawStraightRoadMarkings } from '../rendering/laneMarkings';
import { drawCrossroadSignals, drawTJunctionSignals, drawStraightSignals } from '../rendering/signals';
import { drawVehicle } from '../rendering/vehicles';

interface Props {
  scenario: Scenario;
  controller?: SignalController | null;
  running?: boolean;
  onMetrics?: (metrics: ReturnType<SimulationEngine['getMetrics']>) => void;
}

export function IntersectionCanvas({ scenario, controller, running, onMetrics }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const engineRef = useRef<SimulationEngine | null>(null);
  const frameRef = useRef<number>(0);
  const cxRef = useRef(0);
  const cyRef = useRef(0);

  const initEngine = useCallback(() => {
    const engine = new SimulationEngine(scenario);
    engineRef.current = engine;
    return engine;
  }, [scenario]);

  // Sync running state from parent to engine
  useEffect(() => {
    const engine = engineRef.current;
    if (engine) {
      engine.state.running = running ?? false;
    }
  }, [running]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const engine = initEngine();

    function resize() {
      const parent = canvas!.parentElement;
      if (!parent) return;
      const w = parent.clientWidth;
      const h = parent.clientHeight;
      canvas!.width = w;
      canvas!.height = h;
      cxRef.current = w / 2;
      cyRef.current = h / 2;
      engine.setCenter(cxRef.current, cyRef.current);
    }

    resize();
    window.addEventListener('resize', resize);

    let lastTime = performance.now();
    let metricsTimer = 0;

    function render(now: number) {
      const dt = Math.min((now - lastTime) / 1000, 0.05);
      lastTime = now;

      const cx = cxRef.current;
      const cy = cyRef.current;

      // Update simulation
      if (engine.state.running) {
        engine.step(dt);
      }

      // Draw
      drawBackground(ctx!, canvas!.width, canvas!.height);

      // Road and intersection
      switch (scenario.name) {
        case 'crossroad':
          drawCrossroad(ctx!, cx, cy);
          drawCrossroadMarkings(ctx!, cx, cy);
          drawCrossroadSignals(ctx!, cx, cy, engine.state.currentPhase);
          break;
        case 'tJunction':
          drawTJunction(ctx!, cx, cy);
          drawTJunctionMarkings(ctx!, cx, cy);
          drawTJunctionSignals(ctx!, cx, cy, engine.state.currentPhase);
          break;
        case 'roundabout':
          drawRoundabout(ctx!, cx, cy);
          drawRoundaboutMarkings(ctx!, cx, cy);
          break;
        case 'xIntersection':
          drawXIntersection(ctx!, cx, cy);
          drawCrossroadMarkings(ctx!, cx, cy);
          drawCrossroadSignals(ctx!, cx, cy, engine.state.currentPhase);
          break;
        case 'straightRoad':
          drawStraightRoad(ctx!, cx, cy);
          drawStraightRoadMarkings(ctx!, cx, cy);
          drawStraightSignals(ctx!, cx, cy, engine.state.currentPhase);
          break;
      }

      // Draw vehicles
      for (const v of engine.state.vehicles) {
        const path = engine.getPath(v.approach, v.lane);
        if (!path) continue;
        const pos = getPositionOnPath(path, Math.min(v.distance, path.totalLength));
        drawVehicle(ctx!, v, pos);
      }

      // Report metrics
      metricsTimer += dt;
      if (metricsTimer >= 0.5 && onMetrics) {
        onMetrics(engine.getMetrics());
        metricsTimer = 0;
      }

      frameRef.current = requestAnimationFrame(render);
    }

    frameRef.current = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(frameRef.current);
      window.removeEventListener('resize', resize);
    };
  }, [scenario, initEngine, onMetrics]);

  // Sync controller to engine
  useEffect(() => {
    if (engineRef.current) {
      engineRef.current.controller = controller ?? null;
    }
  }, [controller]);

  // Expose engine methods
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    (canvas as unknown as Record<string, unknown>).__engine = engineRef.current;
  });

  return (
    <canvas
      ref={canvasRef}
      style={{ width: '100%', height: '100%', display: 'block' }}
    />
  );
}

export function getEngine(canvas: HTMLCanvasElement): SimulationEngine | null {
  return (canvas as unknown as Record<string, unknown>).__engine as SimulationEngine ?? null;
}
