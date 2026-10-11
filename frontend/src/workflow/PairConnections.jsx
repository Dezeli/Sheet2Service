import React, { useLayoutEffect, useState } from 'react';

export function connectionPath(start, end, width, stacked) {
  if (stacked) {
    const rail = width - 3;
    return `M ${start.x} ${start.y} C ${rail} ${start.y}, ${rail} ${end.y}, ${end.x} ${end.y}`;
  }
  const middle = (start.x + end.x) / 2;
  return `M ${start.x} ${start.y} C ${middle} ${start.y}, ${middle} ${end.y}, ${end.x} ${end.y}`;
}

export default function PairConnections({ containerRef, revision }) {
  const [drawing, setDrawing] = useState({ width: 1, height: 1, pairs: [] });
  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let frame = 0;
    function measure() {
      const bounds = container.getBoundingClientRect();
      const users = [...container.querySelectorAll('[data-role="user"][data-paired="true"]')];
      const pairs = users.flatMap((user) => {
        const admin = [...container.querySelectorAll('[data-role="admin"][data-paired="true"]')]
          .find((item) => item.dataset.feature === user.dataset.feature);
        if (!admin) return [];
        const left = user.getBoundingClientRect();
        const right = admin.getBoundingClientRect();
        const stacked = right.left < left.right;
        const start = { x: left.right - bounds.left, y: left.top + left.height / 2 - bounds.top };
        const end = { x: (stacked ? right.right : right.left) - bounds.left, y: right.top + right.height / 2 - bounds.top };
        return [{ id: user.dataset.feature, active: user.getAttribute('aria-pressed') === 'true',
          path: connectionPath(start, end, bounds.width, stacked), start, end }];
      });
      setDrawing({ width: bounds.width || 1, height: bounds.height || 1, pairs });
    }
    function schedule() { cancelAnimationFrame(frame); frame = requestAnimationFrame(measure); }
    measure();
    const observer = new ResizeObserver(schedule);
    observer.observe(container);
    container.querySelectorAll('[data-feature]').forEach((item) => observer.observe(item));
    window.addEventListener('resize', schedule);
    return () => { observer.disconnect(); cancelAnimationFrame(frame); window.removeEventListener('resize', schedule); };
  }, [containerRef, revision]);
  return <svg className="workflow-connections" viewBox={`0 0 ${drawing.width} ${drawing.height}`} aria-hidden="true" focusable="false">
    {drawing.pairs.map((pair) => <g key={pair.id} className={pair.active ? 'pair-active' : 'pair-inactive'}>
      <path d={pair.path} />
      <circle cx={pair.start.x} cy={pair.start.y} r="3" /><circle cx={pair.end.x} cy={pair.end.y} r="3" />
    </g>)}
  </svg>;
}
