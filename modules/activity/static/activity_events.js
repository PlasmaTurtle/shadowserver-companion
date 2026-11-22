export function createHandlers() {
  return {
    change: [],
    click: [],
    actions: {},
    forms: {
      'activity-search': async (form, obj) => {
        const params = new URLSearchParams();
        for (const [key, value] of Object.entries(obj))
          if (value.trim()) params.set(key, value.trim());
        location.hash = 'activity?' + params;
      },
    },
  };
}
