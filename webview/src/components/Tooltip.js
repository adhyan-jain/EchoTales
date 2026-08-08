import React from 'react';

export default function Tooltip({ tip }) {
  if (!tip.visible) return null;
  return (
    <div id="tooltip" style={{ display: 'block', left: tip.x + 14, top: tip.y + 14 }}>
      {tip.text}
    </div>
  );
}
