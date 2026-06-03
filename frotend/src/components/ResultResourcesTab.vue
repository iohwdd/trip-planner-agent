<script setup>
import MarkdownContent from "./MarkdownContent.vue";

defineProps({
  result: {
    type: Object,
    required: true
  }
});
</script>

<template>
  <div class="result-grid">
    <article class="info-card">
      <h3>住宿建议</h3>
      <MarkdownContent class="result-markdown" :content="result.accommodation.summary" />
      <ul>
        <li v-for="hotel in result.accommodation.suggested_hotels" :key="hotel.id">
          <MarkdownContent class="result-markdown" :content="`${hotel.name} · ${hotel.address || '地址待确认'}`" />
        </li>
      </ul>
    </article>

    <article class="info-card">
      <h3>美食推荐</h3>
      <ul>
        <li v-for="food in result.food_recommendations" :key="food.id">
          <MarkdownContent class="result-markdown" :content="`${food.name} · ${food.address || '地址待确认'}`" />
        </li>
      </ul>
    </article>

    <article class="info-card">
      <h3>景点候选</h3>
      <ul>
        <li v-for="poi in result.attractions" :key="poi.id">
          <MarkdownContent class="result-markdown" :content="`${poi.name} · ${poi.address || '地址待确认'}`" />
        </li>
      </ul>
    </article>
  </div>
</template>
