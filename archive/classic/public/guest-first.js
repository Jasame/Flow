// 4.5.0: the server may put the guest home's first screen into #app for visitors (guest_first.py). When the address
// carries a hash route such as #login, the app will show something else, so hide that screen at once (flow4.css).
if (location.hash && !/^#(home)?$/.test(location.hash)) document.documentElement.classList.add('flow-hash');
