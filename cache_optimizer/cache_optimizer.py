# -*- coding: utf-8 -*-
import logging
import os
import re
import requests
import hashlib
import tinycss2

from pyquery import PyQuery
from bs4 import BeautifulSoup
from collections import defaultdict

from .sync import Sync
from .config import log_config

log_config()

logger = logging.getLogger(__package__)


CACHE_OPTIMIZED_MARK = '<!--opt-->';
CACHE_HEADER_SEPARATOR = '<!--headers-->';


class Optimizer():
    def __init__(self, site):
        """
        :param site: Dependency injection of object site as it already implements SSH and know
        all relevant information information of the target website
        """
        self.sync = Sync(site, CACHE_OPTIMIZED_MARK)
        self._prepare_output_dir()
        self.files_to_optimize = self.sync.download()

    def _prepare_output_dir(self):
        self.output_dir = self.sync.work_dir + '/04_cache_files_to_upload/'
        os.system('mkdir -p {}'.format(self.output_dir))


    def _load_html_to_keep_classes(self, filename):
        """All classes inside this HTML snippet will be kept in the final optimized file"""
        if not os.path.exists(filename):
            exit('File with HTML to keep classes does not exists: {}'.format(filename))
        self.html_to_keep_classes = open(filename).read()


    def _generate_filename(self, seed, full_path=True, sub_dir=""):
        """
        Generate a unique filename from seed
        :param seed: string used to make the unique filename
        :param full_path: if True, returns the full file path.
        :param sub_dir: subdir to append to work dir
        :return: filename or full path
        """
        filename = hashlib.sha1(seed.encode('utf-8')).hexdigest()[:10]
        if full_path:
            directory = os.path.join(self.sync.work_dir, sub_dir)
            os.system('mkdir -p {}'.format(directory))
            return os.path.join(directory, filename)
        return filename


    def _get_css(self, url):
        """
        Get content and filename of a CSS url and caches to a dictionary, avoiding unnecessary requests.
        :param url: dict with url and filename of css file to be downloaded
        :return:
        """
        if not hasattr(self, 'css'):
            self.css = defaultdict()
        if not self.css.get(url):
            self.css[url] = requests.get(url)
            r = requests.get(url)
            if r.status_code != 200:
                logger.info('Could not download CSS from url: {}'.format(url))
                return False
            # save content and save to file.
            css_filename = '{}.css'.format(self._generate_filename(url, sub_dir='01_downloaded_css'))
            open(css_filename,'w').write(r.text)
            self.css[url] = {'content': r.text, 'file': css_filename, 'url': url}

        return self.css.get(url)



    def _purify_css(self, html, css_file):
        """
        Purify CSS for one html cache filename. Saves an intermediate file including HTML with classes to keep.
        :param html: html content to compare
        :param css_file: css file to match with html
        :return: purified_css content
        """
        # add html to keep classes into the HTML file to be processed
        full_html_file = self._generate_filename(seed=html, sub_dir='02_html_to_purify')
        full_html = html.replace('</body>',self.html_to_keep_classes + '</body>')
        open(full_html_file,'w').write(full_html)

        purified_css_file = self._generate_filename(seed=html, sub_dir='03_css_purified') + '.css'
        c = 'purifycss {} {} --min --out {}'.format(full_html_file, css_file, purified_css_file)
        os.system(c)

        # read created file to return content
        purified_css = open(purified_css_file).read()

        return purified_css, full_html



    def _find_rules_selectors(self, rule):
        """
        Find all selectors for a given CSS rule
        :param rule: rule to find selectors
        :return: list of selectors found
        """
        selectors = []
        # types: QualifiedRule, AtRule, Comment
        if rule.type == 'at-rule' and rule.content:
            ruleList = tinycss2.parse_rule_list(rule.content)
            for r in ruleList:
                selectors += self._find_rules_selectors(r)
            return selectors


        if rule.type == 'qualified-rule':
            rule_selectors = rule.serialize().split('{')[0]
            selectors += rule_selectors.split(',')

        # ignore comments
        if rule.type == 'comment':
            pass

        if rule.type == 'error':
            pass

        # rules not covered (@todo Cover this rules if they showup in any new css library used)
        if rule.type not in ('comment', 'at-rule', 'qualified-rule', 'error', 'whitespace'):
            pass

        return selectors



    def filter_pseudos(self, sel):
        """
        Find possible ocurrencies of pseudo CSS selectors.
        When new CSS rules are created or deprecated, this list must be updated
        """
        pseudos = [
            ':active',
            ':checked',
            ':disabled',
            ':empty',
            ':enabled',
            ':first-child',
            ':first-of-type',
            ':focus',
            ':hover',
            ':in-range',
            ':invalid',
            ':lang(language)',
            ':last-child',
            ':last-of-type',
            ':link',
            ':not',
            ':nth-child',
            ':nth-last-child',
            ':nth-last-of-type',
            ':nth-of-type',
            ':only-of-type',
            ':only-child',
            ':optional',
            ':out-of-range',
            ':read-only',
            ':read-write',
            ':required',
            ':root',
            ':target',
            ':valid',
            ':visited',
            ':after',
            ':before',
            ':first-letter',
            ':first-line',
            ':selection',
            # add all moz pseudo elements
            ':-moz-',
            # add all microsoft pseudo elements
            ':-ms-',
        ]
        if ':' in sel:
            for p in pseudos:

                # first try "::pseudo"
                if ':' + p in sel:
                    return sel.split(p)[0]

                # then try "pseudo"
                if p in sel:
                    return sel.split(p)[0]

                if '::' in sel:
                    # then try "::"
                    return sel.split('::')[0]

        return sel



    def _get_all_selectors(self, css):

        rules = tinycss2.parse_stylesheet(css)
        all_selectors = []

        for rule in rules:
            all_selectors += self._find_rules_selectors(rule)

        # remove pseudoClasses from selectors
        selectors = []
        for sel in all_selectors:
            selectors.append(self.filter_pseudos(sel))

        # unique selectors to match on HTML
        selectors = sorted(list(set(selectors)))

        # logger.debug(selectors)
        return selectors




    def _find_unused_selectors(self, selectors, full_html_file):
        d = PyQuery(full_html_file)
        unused = []
        for sel in selectors:
            if not d(sel):
                unused.append(sel)

        # logger.info('Total unused selectors to be removed: {}'.format(len(unused)))
        return unused

    def _is_css_valid(self, css):
        # check if css if valid
        rules = tinycss2.parse_stylesheet(css)
        for r in rules:
            if r.type == 'error': return False
        return True


    def _remove_unused_selectors_from_rule(self, rule, unused):

        new_css = ''

        # ignore @media queries
        if rule.type == 'at-rule' and rule.lower_at_keyword == 'media':
            rule_list = tinycss2.parse_rule_list(rule.content)
            new_css = ''
            for r in rule_list:
                # recursion to deal with @media elements
                css = self._remove_unused_selectors_from_rule(r, unused)
                new_css += css

            # reconstruct media CSS if any rule is left inside @media
            if new_css:
                media_css = '@media'
                for node in rule.prelude:
                    media_css += node.serialize()
                    # log.debug(node.serialize())

                media_css = media_css + '{' + new_css + '}'

                return media_css
            else:
                return ''

        # check if there are any used selectors
        rule_css = rule.serialize()
        selectors = self._get_all_selectors(rule_css)
        selectors_left = selectors[:]

        for sel in selectors:
            if sel in unused:
                selectors_left.remove(sel)

                # .nav,.sidebar li,.thumbnails{list-style:none}
                # remove class: .thumbnails
                rule_css = rule_css.replace(',' + sel + '{', '{')

                # remove class: .sidebar li or .nav
                rule_css = rule_css.replace(sel + ',', '')

                # remove class: .nav{
                rule_css = rule_css.replace(sel + '{', '{')

        # if any selector left... uses the remaining css
        if selectors_left:
            if self._is_css_valid(rule_css):
                new_css += rule_css
            else:
                logger.error('Invalid CSS rule detected after removing unused classes!')
                logger.error(rule_css)
                exit()

        return new_css




    def _remove_unused_selectors(self, css, unused):
        """Remove all unused rules from CSS"""
        new_css = ''
        rules = tinycss2.parse_stylesheet(css)
        for rule in rules[:]:
            rule_css = self._remove_unused_selectors_from_rule(rule, unused)
            new_css += rule_css
        # new_css = new_css.encode('utf8')
        return new_css


    def _inline_css(self, html, css, style_tag):
        if not css:
            logger.error('CSS to inline is empty!')
            exit()

        pat = r"<link[^>]*\.css[^>]*>"
        css_link = re.search(pat, html).group(0)
        html = html.replace(css_link, '')
        html = html.replace('</head>', '<style>' + css + '</style>')
        html = html.replace('</style><style>', '')

        # bad smell.. but removes specific tokens inserted on customized WordPress theme.
        html = html.replace('___adsense_CSS_here___', '')
        html += CACHE_OPTIMIZED_MARK
        return html



    def _optimize_file(self, cache_filename):
        """Optimize a single file."""
        cache_header, html = open(cache_filename, 'r').read().split(CACHE_HEADER_SEPARATOR)

        soup = BeautifulSoup(html, "html.parser")
        title = soup.find('title').text

        style_tag = soup.find('link', {"rel":"stylesheet"})

        if not style_tag:
            logger.info('HTML does not contain a css file in a tag <link>')
            return False

        css_url = style_tag.get('href','')
        css = self._get_css(css_url)

        purified_css, full_html = self._purify_css(html, css.get('file'))

        selectors = self._get_all_selectors(purified_css)
        # logger.debug("Total selectors found: {}".format(len(selectors)))

        unused_selectors = self._find_unused_selectors(selectors, full_html)

        clean_css = self._remove_unused_selectors(purified_css, unused_selectors)

        new_html = self._inline_css(html, clean_css, style_tag)

        new_cache_file_content = cache_header + CACHE_HEADER_SEPARATOR + new_html

        output_cache_file = '{}{}'.format(self.output_dir, os.path.basename(cache_filename))

        # logger.debug(output_cache_file)
        open(output_cache_file,'w').write(new_cache_file_content)
        self._print_stats(title, cache_header + html, css.get('content'), new_html)


    def _print_stats(self, title, html_before, css_before, html_after):
        html_before_size = len(html_before)
        css_before_size = len(css_before)
        html_after_size = len(html_after)

        logger.info('{}: ({}+{}={}) -> ({}) = {:3.2f}%'.format(
            title,
            html_before_size,
            css_before_size,
            html_before_size + css_before_size,
            html_after_size,
            100*((html_after_size / (html_before_size + css_before_size)))
        ))




    def optimize_all_files(self, keep_html_classes_file):
        """
        Optimize in parallel all files downloaded
        :return: list of final optimized files to be uploaded.
        """
        self._load_html_to_keep_classes(filename=keep_html_classes_file)

        logger.info('Total files to optimize: {}'.format(len(self.files_to_optimize)))

        for f in self.files_to_optimize:
            self._optimize_file(f)



