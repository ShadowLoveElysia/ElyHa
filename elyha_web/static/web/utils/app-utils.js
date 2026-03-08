(function () {
  "use strict";

  window.ElyhaWebAppUtils = {
    hashString: function (value) {
      let hash = 0;
      const str = String(value || "");
      for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i);
        hash = (hash << 5) - hash + char;
        hash = hash & hash;
      }
      return hash;
    },

    storylineColor: function (storylineId) {
      const colors = ["#3b82f6", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#06b6d4", "#6366f1"];
      const hash = this.hashString(storylineId);
      const index = Math.abs(hash) % colors.length;
      return colors[index];
    },

    clampZoom: function (value, min, max) {
      return Math.min(max, Math.max(min, value));
    }
  };
})();
