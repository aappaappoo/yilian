<template>
  <h1 class="hero-art-title" aria-label="此刻，想与哪位陪伴者相遇？">
    <svg class="hero-art-title__svg" viewBox="0 0 1100 360" role="img" aria-hidden="true">
      <defs>
        <linearGradient id="heroLogoText" x1="280" y1="34" x2="760" y2="292" gradientUnits="userSpaceOnUse">
          <stop offset="0" stop-color="#f6e9ff" />
          <stop offset="0.18" stop-color="#d2b4ff" />
          <stop offset="0.54" stop-color="#9b73e6" />
          <stop offset="1" stop-color="#6d46bd" />
        </linearGradient>

        <linearGradient id="heroLogoSideTint" x1="240" y1="96" x2="830" y2="292" gradientUnits="userSpaceOnUse">
          <stop offset="0" stop-color="#fff8ff" stop-opacity="0.7" />
          <stop offset="0.5" stop-color="#d9c6ff" stop-opacity="0.24" />
          <stop offset="1" stop-color="#6f45bf" stop-opacity="0.08" />
        </linearGradient>

        <linearGradient id="heroLogoHighlight" x1="260" y1="46" x2="610" y2="176" gradientUnits="userSpaceOnUse">
          <stop offset="0" stop-color="#fffaff" stop-opacity="0.98" />
          <stop offset="0.5" stop-color="#fffaff" stop-opacity="0.34" />
          <stop offset="1" stop-color="#fffaff" stop-opacity="0" />
        </linearGradient>

        <linearGradient id="heroLogoLine" x1="98" y1="292" x2="980" y2="76" gradientUnits="userSpaceOnUse">
          <stop offset="0" stop-color="#8d71e8" stop-opacity="0" />
          <stop offset="0.18" stop-color="#8b75e9" stop-opacity="0.38" />
          <stop offset="0.48" stop-color="#ff9bc7" stop-opacity="0.32" />
          <stop offset="0.78" stop-color="#a78df4" stop-opacity="0.34" />
          <stop offset="1" stop-color="#8d71e8" stop-opacity="0" />
        </linearGradient>

        <radialGradient id="heroLogoSpark" cx="50%" cy="50%" r="50%">
          <stop offset="0" stop-color="#fffaff" stop-opacity="1" />
          <stop offset="0.52" stop-color="#d1b7ff" stop-opacity="0.82" />
          <stop offset="1" stop-color="#a987f3" stop-opacity="0" />
        </radialGradient>

        <linearGradient id="heroLogoPetal" x1="0" y1="0" x2="28" y2="24" gradientUnits="userSpaceOnUse">
          <stop offset="0" stop-color="#ffe3f1" stop-opacity="0.98" />
          <stop offset="0.52" stop-color="#ff9fcc" stop-opacity="0.72" />
          <stop offset="1" stop-color="#ff77b8" stop-opacity="0.18" />
        </linearGradient>

        <filter id="heroLogoOuterGlow" x="-16%" y="-26%" width="132%" height="160%">
          <feGaussianBlur in="SourceAlpha" stdDeviation="5.5" result="wideGlow" />
          <feColorMatrix
            in="wideGlow"
            type="matrix"
            values="0 0 0 0 0.56 0 0 0 0 0.38 0 0 0 0 0.95 0 0 0 0.24 0"
            result="purpleGlow"
          />
          <feMerge>
            <feMergeNode in="purpleGlow" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>

        <filter id="heroLogoSoftBlur" x="-16%" y="-26%" width="132%" height="160%">
          <feGaussianBlur stdDeviation="4.5" />
        </filter>

        <filter id="heroLogoTinyGlow" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <g class="hero-art-title__halo">
        <ellipse cx="524" cy="176" rx="390" ry="112" />
      </g>

      <g class="hero-art-title__ribbons">
        <path class="hero-art-title__ribbon hero-art-title__ribbon--left" d="M92 218 C162 275, 294 250, 368 172" />
        <path class="hero-art-title__ribbon hero-art-title__ribbon--upper" d="M630 112 C733 31, 916 48, 861 157 C834 210, 742 218, 688 184" />
        <path class="hero-art-title__ribbon hero-art-title__ribbon--lower" d="M156 283 C350 333, 708 318, 902 249" />
        <path class="hero-art-title__ribbon hero-art-title__ribbon--thread" d="M224 155 C342 92, 512 84, 634 132 C746 176, 810 158, 894 108" />
        <path class="hero-art-title__ribbon hero-art-title__ribbon--inner" d="M286 255 C426 286, 610 284, 754 244" />
      </g>

      <g class="hero-art-title__swashes">
        <path d="M294 101 C338 56, 400 62, 401 100 C402 125, 362 136, 338 115" />
        <path d="M328 129 C292 164, 222 158, 198 120" />
        <path d="M274 224 C232 270, 150 274, 116 229" />
        <path d="M448 203 C524 151, 648 164, 664 214 C674 242, 620 264, 570 237" />
        <path d="M516 262 C596 304, 760 285, 898 233" />
      </g>

      <g class="hero-art-title__main-text">
        <text class="hero-art-title__text hero-art-title__text--top" x="190" y="112">此刻，想与哪位</text>
        <text class="hero-art-title__text hero-art-title__text--bottom" x="232" y="240">陪伴者相遇？</text>
      </g>

      <g class="hero-art-title__shine" aria-hidden="true">
        <text class="hero-art-title__shine-text hero-art-title__shine-text--top" x="190" y="112">此刻，想与哪位</text>
        <text class="hero-art-title__shine-text hero-art-title__shine-text--bottom" x="232" y="240">陪伴者相遇？</text>
      </g>

      <g class="hero-art-title__edge-light" aria-hidden="true">
        <path d="M310 66 C360 45, 438 54, 500 78" />
        <path d="M356 166 C478 132, 646 146, 760 190" />
        <path d="M730 230 C778 219, 830 202, 874 176" />
      </g>

      <g class="hero-art-title__petals">
        <path d="M104 232 C119 212, 142 220, 134 244 C122 250, 111 244, 104 232Z" />
        <path d="M170 139 C183 124, 204 131, 197 151 C184 158, 176 151, 170 139Z" />
        <path d="M906 216 C922 199, 946 207, 938 229 C924 236, 913 228, 906 216Z" />
      </g>

      <g class="hero-art-title__sparkles">
        <path class="hero-art-title__sparkle hero-art-title__sparkle--large" d="M800 46 L810 72 L836 82 L810 92 L800 118 L790 92 L764 82 L790 72Z" />
        <path class="hero-art-title__sparkle" d="M130 161 L136 177 L152 183 L136 189 L130 205 L124 189 L108 183 L124 177Z" />
        <path class="hero-art-title__sparkle" d="M928 136 L934 152 L950 158 L934 164 L928 180 L922 164 L906 158 L922 152Z" />
        <circle cx="214" cy="196" r="4.5" />
        <circle cx="738" cy="122" r="4" />
        <circle cx="842" cy="274" r="3.5" />
      </g>
    </svg>
  </h1>
</template>

<style scoped lang="scss">
.hero-art-title {
  position: relative;
  margin: 0;
  width: min(1080px, 100%);
  height: clamp(214px, 21vw, 360px);
  overflow: visible;
}

.hero-art-title__svg {
  display: block;
  width: 100%;
  height: 100%;
  overflow: visible;
}

.hero-art-title__halo {
  fill: rgba(255, 244, 253, 0.5);
  filter: blur(12px);
  opacity: 0.58;
}

.hero-art-title__text,
.hero-art-title__shine-text {
  font-family: var(--soulmeet-font-family);
  text-anchor: start;
  dominant-baseline: alphabetic;
  letter-spacing: 0.055em;
  transform-box: fill-box;
  transform-origin: center;
}

.hero-art-title__text--top,
.hero-art-title__shine-text--top {
  font-size: 82px;
  transform: scaleX(1.04);
}

.hero-art-title__text--bottom,
.hero-art-title__shine-text--bottom {
  font-size: 132px;
  letter-spacing: 0.025em;
  transform: scaleX(1.02);
}

.hero-art-title__main-text {
  fill: url("#heroLogoText");
  filter: url("#heroLogoOuterGlow");
  font-weight: 600;
  paint-order: stroke fill;
  stroke: url("#heroLogoSideTint");
  stroke-width: 0.58;
}

.hero-art-title__main-text .hero-art-title__text--top {
  opacity: 0.98;
}

.hero-art-title__shine {
  fill: url("#heroLogoHighlight");
  opacity: 0.62;
  pointer-events: none;
}

.hero-art-title__ribbon,
.hero-art-title__swashes path,
.hero-art-title__edge-light path {
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
  vector-effect: non-scaling-stroke;
}

.hero-art-title__ribbon {
  stroke: url("#heroLogoLine");
  stroke-width: 1.25;
  opacity: 0.62;
}

.hero-art-title__ribbon--lower {
  stroke-width: 0.95;
  opacity: 0.48;
}

.hero-art-title__ribbon--thread {
  stroke-width: 0.75;
  opacity: 0.36;
}

.hero-art-title__ribbon--inner {
  stroke-width: 0.7;
  opacity: 0.28;
}

.hero-art-title__swashes path {
  stroke: url("#heroLogoLine");
  stroke-width: 1.05;
  opacity: 0.42;
}

.hero-art-title__swashes path:nth-child(2),
.hero-art-title__swashes path:nth-child(3),
.hero-art-title__swashes path:nth-child(5) {
  stroke-width: 0.76;
  opacity: 0.3;
}

.hero-art-title__edge-light path {
  stroke: rgba(255, 250, 255, 0.54);
  stroke-width: 0.9;
  opacity: 0.56;
  filter: blur(0.2px);
}

.hero-art-title__sparkles {
  fill: url("#heroLogoSpark");
  filter: url("#heroLogoTinyGlow");
  opacity: 0.76;
}

.hero-art-title__sparkle {
  transform-box: fill-box;
  transform-origin: center;
}

.hero-art-title__sparkle--large {
  opacity: 0.86;
}

.hero-art-title__petals {
  fill: url("#heroLogoPetal");
  filter: drop-shadow(0 8px 14px rgba(255, 126, 190, 0.16));
  opacity: 0.76;
}

@media (max-width: 980px) {
  .hero-art-title {
    height: clamp(170px, 44vw, 246px);
  }
}
</style>
