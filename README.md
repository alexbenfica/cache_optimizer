Cache Optimizer
========================

This optimizer helps your pages to get a PageSpeed Score close to the 100, which tend to be important to achieve a better rankings on Google.

It has a very specific application as the cache files are created by a customized and optimized version of an old WordPress plugin called Quick Cache. It is public here as the code might be useful for others trying to achieve similar results.

Not only the posts or home page but every single URL in a WordPress site generates a cache file.
A medium size WordPress blog might have thousands of cache files.

The advantage of this approach is that it runs in a different server, offloading the web server from doing it when creating the cache file.

## What it does:
- download \ rsync cache files created for a WordPress blog and "optimize" files still not optimized.
- remove CSS classes, pseudo-classes, rules and selectors that are not referenced inside the HTML
- validate the remaining CSS
- combine and inline the remaining CSS files as the resulting CSS is usually very small
- send optimized files back to server via rsync (super fast)
- it runs as a cron scheduled command of Flask app via Flask-CLI

## The result is:
- optimized pages loads a lot faster
- as the CSS files are now inline, HTML file is a little bigger, but the page full renders with 1 single HTML request.
- on average, on the target websites, page views per user is close to 2, so one request less means almost 30% less total requests to the web server
- server can handle more concurrent requests.

## Downsides:
- no CSS files can be cached between requests to a page as it is now inline
- called from flask-cli inside a Docker container
- remote cache directory on target website MUST be accessible and writable using ssh keys
- processing is almost one second per cache file, even with optimizations

Also depends on:
https://github.com/purifycss/purifycss
