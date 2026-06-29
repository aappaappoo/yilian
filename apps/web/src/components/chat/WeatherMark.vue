<script setup lang="ts">
import type { PropType } from 'vue'

defineProps({
  kind: { type: String, default: 'partly' },
  size: {
    type: String as PropType<'tiny' | 'regular' | 'large'>,
    default: 'regular',
  },
})
</script>

<template>
  <span class="weather-mark" :class="[`weather-mark--${kind}`, `weather-mark--${size}`]" aria-hidden="true">
    <span class="weather-mark__sun"></span>
    <span class="weather-mark__cloud weather-mark__cloud--main"></span>
    <span class="weather-mark__cloud weather-mark__cloud--soft"></span>
    <span class="weather-mark__rain">
      <i></i>
      <i></i>
      <i></i>
    </span>
    <span class="weather-mark__snow">
      <i></i>
      <i></i>
      <i></i>
    </span>
    <span class="weather-mark__mist">
      <i></i>
      <i></i>
      <i></i>
    </span>
  </span>
</template>

<style scoped>
.weather-mark {
  position: relative;
  display: inline-block;
  width: 52px;
  height: 52px;
  flex: 0 0 auto;
  overflow: visible;
  border-radius: 18px;
  filter: drop-shadow(0 12px 16px rgba(109, 86, 160, 0.16));
}

.weather-mark--tiny {
  width: 34px;
  height: 34px;
  border-radius: 13px;
  filter: drop-shadow(0 7px 10px rgba(109, 86, 160, 0.13));
}

.weather-mark--large {
  width: 82px;
  height: 76px;
  border-radius: 22px;
}

.weather-mark__sun {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 27px;
  height: 27px;
  border-radius: 999px;
  background: radial-gradient(circle at 32% 28%, #fff8c7 0 24%, #facc15 48%, #f97316 100%);
  box-shadow:
    0 0 0 6px rgba(250, 204, 21, 0.18),
    0 5px 12px rgba(249, 115, 22, 0.22);
}

.weather-mark__cloud {
  position: absolute;
  border-radius: 999px;
  background: linear-gradient(145deg, #ffffff 0%, #e8edff 54%, #cbd5e1 100%);
  box-shadow: 0 7px 12px rgba(100, 116, 139, 0.18);
}

.weather-mark__cloud::before,
.weather-mark__cloud::after {
  content: "";
  position: absolute;
  border-radius: 999px;
  background: inherit;
}

.weather-mark__cloud--main {
  right: 8px;
  bottom: 16px;
  width: 37px;
  height: 14px;
}

.weather-mark__cloud--main::before {
  left: 6px;
  bottom: 5px;
  width: 15px;
  height: 15px;
}

.weather-mark__cloud--main::after {
  right: 5px;
  bottom: 4px;
  width: 12px;
  height: 12px;
}

.weather-mark__cloud--soft {
  right: 29px;
  bottom: 13px;
  width: 17px;
  height: 8px;
  opacity: 0.74;
}

.weather-mark__cloud--soft::before {
  left: 4px;
  bottom: 2px;
  width: 8px;
  height: 8px;
}

.weather-mark__cloud--soft::after {
  display: none;
}

.weather-mark__rain,
.weather-mark__snow,
.weather-mark__mist {
  position: absolute;
  left: 12px;
  right: 10px;
  bottom: 4px;
  height: 13px;
}

.weather-mark__rain i {
  position: absolute;
  top: 0;
  width: 4px;
  height: 11px;
  border-radius: 999px 999px 999px 2px;
  background: linear-gradient(180deg, #60a5fa, #2563eb);
  box-shadow: 0 2px 5px rgba(37, 99, 235, 0.24);
  transform: rotate(16deg);
}

.weather-mark__rain i:nth-child(1) {
  left: 4px;
}

.weather-mark__rain i:nth-child(2) {
  left: 15px;
  top: 3px;
}

.weather-mark__rain i:nth-child(3) {
  left: 26px;
}

.weather-mark__snow i {
  position: absolute;
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: #f8fdff;
  box-shadow:
    0 0 0 2px rgba(125, 211, 252, 0.42),
    0 3px 7px rgba(8, 145, 178, 0.18);
}

.weather-mark__snow i:nth-child(1) {
  left: 4px;
  top: 1px;
}

.weather-mark__snow i:nth-child(2) {
  left: 15px;
  top: 7px;
}

.weather-mark__snow i:nth-child(3) {
  left: 27px;
  top: 2px;
}

.weather-mark__mist i {
  position: absolute;
  right: 0;
  height: 3px;
  border-radius: 999px;
  background: linear-gradient(90deg, rgba(203, 213, 225, 0.42), #64748b);
  box-shadow: 0 3px 8px rgba(100, 116, 139, 0.16);
}

.weather-mark__mist i:nth-child(1) {
  top: 0;
  width: 29px;
}

.weather-mark__mist i:nth-child(2) {
  top: 6px;
  width: 22px;
}

.weather-mark__mist i:nth-child(3) {
  top: 12px;
  width: 32px;
}

.weather-mark--sunny {
  background: transparent;
}

.weather-mark--sunny .weather-mark__sun {
  top: 10px;
  right: 12px;
  width: 34px;
  height: 34px;
}

.weather-mark--sunny .weather-mark__cloud,
.weather-mark--sunny .weather-mark__rain,
.weather-mark--sunny .weather-mark__snow,
.weather-mark--sunny .weather-mark__mist,
.weather-mark--partly .weather-mark__rain,
.weather-mark--partly .weather-mark__snow,
.weather-mark--partly .weather-mark__mist,
.weather-mark--cloudy .weather-mark__sun,
.weather-mark--cloudy .weather-mark__rain,
.weather-mark--cloudy .weather-mark__snow,
.weather-mark--cloudy .weather-mark__mist,
.weather-mark--rain .weather-mark__snow,
.weather-mark--rain .weather-mark__mist,
.weather-mark--snow .weather-mark__rain,
.weather-mark--snow .weather-mark__mist,
.weather-mark--fog .weather-mark__sun,
.weather-mark--fog .weather-mark__rain,
.weather-mark--fog .weather-mark__snow {
  display: none;
}

.weather-mark--cloudy {
  background: transparent;
}

.weather-mark--cloudy .weather-mark__cloud--main {
  right: 8px;
  bottom: 18px;
  transform: scale(1.1);
}

.weather-mark--cloudy .weather-mark__cloud--soft {
  right: 23px;
  bottom: 15px;
  transform: scale(1.08);
}

.weather-mark--rain {
  background: transparent;
}

.weather-mark--rain .weather-mark__sun,
.weather-mark--snow .weather-mark__sun {
  opacity: 0.32;
}

.weather-mark--snow {
  background: transparent;
}

.weather-mark--snow .weather-mark__cloud {
  background: linear-gradient(145deg, #ffffff 0%, #edf8ff 58%, #bae6fd 100%);
}

.weather-mark--fog {
  background: transparent;
}

.weather-mark--fog .weather-mark__cloud {
  opacity: 0.74;
}

.weather-mark--tiny .weather-mark__sun {
  top: 6px;
  right: 6px;
  width: 15px;
  height: 15px;
  box-shadow:
    0 0 0 4px rgba(250, 204, 21, 0.16),
    0 3px 8px rgba(249, 115, 22, 0.18);
}

.weather-mark--tiny .weather-mark__cloud--main {
  right: 6px;
  bottom: 10px;
  width: 22px;
  height: 9px;
}

.weather-mark--tiny .weather-mark__cloud--main::before {
  left: 4px;
  bottom: 3px;
  width: 10px;
  height: 10px;
}

.weather-mark--tiny .weather-mark__cloud--main::after {
  right: 4px;
  bottom: 3px;
  width: 8px;
  height: 8px;
}

.weather-mark--tiny .weather-mark__cloud--soft {
  right: 17px;
  bottom: 8px;
  width: 12px;
  height: 6px;
}

.weather-mark--tiny .weather-mark__rain,
.weather-mark--tiny .weather-mark__snow,
.weather-mark--tiny .weather-mark__mist {
  left: 7px;
  right: 6px;
  bottom: 2px;
  height: 9px;
}

.weather-mark--tiny .weather-mark__rain i {
  width: 3px;
  height: 8px;
}

.weather-mark--tiny .weather-mark__rain i:nth-child(1),
.weather-mark--tiny .weather-mark__snow i:nth-child(1) {
  left: 3px;
}

.weather-mark--tiny .weather-mark__rain i:nth-child(2),
.weather-mark--tiny .weather-mark__snow i:nth-child(2) {
  left: 11px;
  top: 3px;
}

.weather-mark--tiny .weather-mark__rain i:nth-child(3),
.weather-mark--tiny .weather-mark__snow i:nth-child(3) {
  left: 19px;
}

.weather-mark--tiny .weather-mark__snow i {
  width: 4px;
  height: 4px;
}

.weather-mark--tiny .weather-mark__mist i {
  height: 2px;
}

.weather-mark--tiny .weather-mark__mist i:nth-child(1) {
  width: 20px;
}

.weather-mark--tiny .weather-mark__mist i:nth-child(2) {
  top: 5px;
  width: 15px;
}

.weather-mark--tiny .weather-mark__mist i:nth-child(3) {
  top: 10px;
  width: 21px;
}

.weather-mark--large .weather-mark__sun {
  top: 8px;
  right: 9px;
  width: 42px;
  height: 42px;
}

.weather-mark--large .weather-mark__cloud--main {
  right: 10px;
  bottom: 22px;
  width: 56px;
  height: 20px;
}

.weather-mark--large .weather-mark__cloud--main::before {
  width: 19px;
  height: 19px;
}

.weather-mark--large .weather-mark__cloud--main::after {
  width: 16px;
  height: 16px;
}
</style>
