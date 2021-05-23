/*
 * Copyright (C) 2017-2021 Chris Hager and all contributors.
 * 
 * This is "vue-highlightjs" related code and licensed under the MIT license.
 *
 * For more infomation about "vue-highlightjs",
 * see https://github.com/metachris/vue-highlightjs
 */

Vue.directive('highlightjs', {
  deep: true,
  bind: function bind(el, binding) {
    // on first bind, highlight all targets
    var targets = el.querySelectorAll('code');
    var target;
    var i;

    for (i = 0; i < targets.length; i += 1) {
      target = targets[i];

      if (typeof binding.value === 'string') {
        // if a value is directly assigned to the directive, use this
        // instead of the element content.
        target.textContent = binding.value;
      }

      hljs.highlightElement(target);
    }
  },
  componentUpdated: function componentUpdated(el, binding) {
    // after an update, re-fill the content and then highlight
    var targets = el.querySelectorAll('code');
    var target;
    var i;

    for (i = 0; i < targets.length; i += 1) {
      target = targets[i];
      if (typeof binding.value === 'string') {
        target.textContent = binding.value;
      }
      hljs.highlightElement(target);
    }
  }
});
