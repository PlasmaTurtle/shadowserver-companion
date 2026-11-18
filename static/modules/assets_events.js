/** Delegated asset actions; each lookup is asynchronous and cancellable. */
export function createHandlers(ctx) {
  return {
    change: [],
    click: [
      {
        matches: (el) => el.dataset.attributeAsset,
        run: (el) =>
          ctx.actions.busy(el, () => ctx.actions.startAssetAttribution(el.dataset.attributeAsset)),
      },
      {
        matches: (el) => el.dataset.assetResult,
        run: (el) =>
          ctx.actions.busy(el, () => ctx.actions.showAssetResult(el.dataset.assetResult)),
      },
      {
        matches: (el) => el.dataset.adoptAsset,
        run: (el) =>
          ctx.actions.busy(el, () => ctx.actions.adoptAssetAttribution(el.dataset.adoptAsset)),
      },
    ],
    forms: {},
    actions: {
      'attribute-remaining': () => ctx.actions.startAssetAttribution(),
      'cancel-asset-attribution': () => ctx.actions.cancelAssetAttribution(),
      'refresh-asset-attribution': () => ctx.actions.loadAssetAttribution(),
    },
  };
}
