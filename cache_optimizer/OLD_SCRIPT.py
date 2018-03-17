# -*- coding: utf-8 -*-
import requests
import logging
import urllib2
import re
import os
import hashlib
import argparse
import pprint
import shutil
import time

from multiprocessing import Pool

import tinycss2
from html5print import CSSBeautifier
from pyquery import PyQuery as pq


# http://www.rueckstiess.net/research/snippets/show/ca1d7d90
def unwrap_self(arg, **kwarg):
    return clearCss.processFile(*arg, **kwarg)


class clearCss():
    def __init__(self, rootDir, remoteCachePath, ignoreTemplate):
        # self.optimizedMark = '<!--optm-->';
        # self.cacheHeaderSeparator = '<!--headers-->';
        self.loadIgnoreTemplate(ignoreTemplate)
        self.rootDir = rootDir
        self.remoteCachePath = remoteCachePath
        log.info('Removing unused css classes from cache files in: %s' % rootDir)
        self.prepareDirs()
        self.downloadCacheFiles()

        start_time = time.time()

        # self.processAllFiles()
        self.processAllFilesInParallel()

        totalFiles = len(self.filesToProcess)
        totalTimeInSeconds = time.time() - start_time
        filesPerSecond = totalFiles / totalTimeInSeconds

        if 1:
            self.uploadCacheFiles()
        else:
            log.info('Files were not uploaded back to server... Debug!')

        log.info('Total time to proccess %d files: %.2f seconds. %.2f files per second!' %
                 (totalFiles, totalTimeInSeconds, filesPerSecond))

    def loadIgnoreTemplate(self, ignoreFileName):
        self.ignoreHTML = ''
        self.ignoreFileName = ignoreFileName
        if not ignoreFileName: return
        if not os.path.isfile(ignoreFileName):
            exit('Ignore list file does not exists: %s' % ignoreFileName)
        self.ignoreHTML = open(ignoreFileName, 'r').read().strip()

    def prepareDirs(self):
        log.info('Preparing directories to receive cache files from server...')

        self.cacheDownloadDir = self.rootDir + '000_cache_download/'
        self.cssdir = self.rootDir + '020_original_css/'
        self.htmlToPurifyDir = self.rootDir + '030_html_to_purify/'
        self.cssPurifiedDir = self.rootDir + '040_purified_css/'
        self.cssOptimizedDir = self.rootDir + '050_optimized_css/'
        self.cacheUploadDir = self.rootDir + '060_cache_upload/'

        if os.path.isdir(self.rootDir): shutil.rmtree(self.rootDir)

        dirs = [self.cacheDownloadDir]
        dirs.append(self.rootDir)
        dirs.append(self.cacheDownloadDir)
        dirs.append(self.cssdir)
        dirs.append(self.htmlToPurifyDir)
        dirs.append(self.cssPurifiedDir)
        dirs.append(self.cssOptimizedDir)
        dirs.append(self.cacheUploadDir)
        for d in dirs:
            if not os.path.isdir(d):
                os.makedirs(d)

        log.info('Directories ready to go!')


    def uploadCacheFiles(self):
        # re-send and update cache files on server
        command = 'rsync -ca %s%s %s' % (self.cacheUploadDir, 'qc-c*', self.remoteCachePath)
        print
        'Uploading modified cache files to server...'
        # print command
        os.system(command)



    def processFile(self, f):
        cacheFileName = self.cacheDownloadDir + f
        self.baseFileName = f

        msg = ''
        msg += "\n" + 'Processing: %s' % (cacheFileName)

        # self.originFiles[f] = {}
        # self.originFiles[f]['original_html_file'] = htmlFile

        header, html = open(cacheFileName, 'r').read().split(self.cacheHeaderSeparator)
        # self.originFiles[f]['original_html'] = html

        title = self.getPageTitleFromHtml(html)
        msg += "\n" + 'Page title -> %s' % title

        # save HTML that will be used to purify
        htmlToFindClasses = html.replace('</body>', self.ignoreHTML + '</body>')
        htmlToFindClassesFile = self.htmlToPurifyDir + f + '.html'
        open(htmlToFindClassesFile, 'w').write(htmlToFindClasses)

        cssUrl = self.getCssUrls(html)

        if not cssUrl:
            msg += 'Could not find a CSS url inside cache file!'
            return

        cssFile, css = self.downloadCss(cssUrl)

        if not cssFile:
            msg += 'Could not download CSS file: %s  ' % cssUrl
            return

        cssOptimFile, cssOptim = self.purifycss(htmlToFindClassesFile, cssFile)

        selectors = self.getAllCssSelectors(cssOptim)

        unusedSelectors = self.findUnusedSelectors(htmlToFindClasses, selectors)

        cssOptim = self.removeUnusedSelectors(cssOptim, unusedSelectors)

        # exit()

        html_after = self.inlineCss(header, html, cssOptim, cacheFileName)

        msg += "\n" + self.printStats('CSS file (now inline)', css, cssOptim, 1)
        msg += "\n" + self.printStats('HTML file (single request)', html, html_after, 1)
        msg += "\n"

        return msg

    def processAllFiles(self):
        # list all files to be processed
        files = self.listFilesToProcess()

        print
        '%d files to process!' % len(files)

        iFile = 0
        for f in files:
            iFile += 1
            self.processFile(f)
            # break

    def processAllFilesInParallel(self):
        files = self.listFilesToProcess()
        pool = Pool()
        results = pool.map(unwrap_self, zip([self] * len(files), files))

        for r in results:
            if r:
                log.info(r)

    def downloadCss(self, url):
        if not url: return '', ''

        cssfile = self.cssdir + hashlib.sha224(url).hexdigest() + '.css'

        if os.path.exists(cssfile):
            # print 'CSS already downloaded. Using file for url %s' % url
            content = open(cssfile, 'r').read()
        else:
            log.info('Downloading CSS file: %s' % url)
            r = requests.get(url)
            if r.status_code <> 200:
                log.info('Could not download css file. HTTP code %d' % r.status_code)
                log.info('CSS url was: %s' % url)
                return '', ''

            content = r.text.encode(r.encoding)
            open(cssfile, 'w').write(content)

        return cssfile, content

    def purifycss(self, htmlFile, cssFile):
        if not cssFile: return '', ''

        outputCssFile = self.cssPurifiedDir + self.baseFileName + '.css'

        if not os.path.exists(outputCssFile):
            # log.info('Purifying CSS to file: ' + outputCssFile)
            command = 'purifycss '
            command += ' ' + htmlFile
            command += ' ' + cssFile
            command += ' --min '
            # command += ' --info '
            command += ' --out ' + outputCssFile
            print
            command
            os.system(command)
        else:
            pass
            # log.info('Purified CSS file already exists. ')
            # log.info('Loading purified from file: ' + outputCssFile)

        # self.printStats('Unused rules remotion',open(cssFile,'r').read(), open(outputCssFile,'r').read())

        # return outputCssFile, open(cssFile,'r').read()
        return outputCssFile, open(outputCssFile, 'r').read()

    def findRuleSelectors(self, rule, unUsed=[]):
        selectors = []

        # types: QualifiedRule, AtRule, Comment
        if rule.type == 'at-rule':
            ruleList = tinycss2.parse_rule_list(rule.content)
            for r in ruleList:
                selectors += self.findRuleSelectors(r)

                # log.debug(rule.serialize())
            # log.debug(selectors)
            return selectors
            # exit()

        if rule.type == 'qualified-rule':
            # print rule.serialize()
            rule_selectors = rule.serialize().split('{')[0]
            selectors += rule_selectors.split(',')

        if rule.type == 'comment':
            # print 'Comment ignored!'
            pass

        if rule.type == 'error':
            log.debug(rule.kind)
            log.debug(rule.message)
            pass
            # exit()

        if rule.type not in ('comment', 'at-rule', 'qualified-rule', 'error', 'whitespace'):
            print
            'Rule type not covered: %s' % rule.type
            exit()

        # print selectors
        # print
        return selectors

    def filterPseudo(self, sel):
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
                    sel = sel.split(p)[0]
                    return sel

                # then try "::pseudo"
                if p in sel:
                    sel = sel.split(p)[0]
                    return sel

                if '::' in sel:
                    # then try "::"
                    sel = sel.split('::')[0]
                    return sel

        return sel

    def getAllCssSelectors(self, css):
        rules = tinycss2.parse_stylesheet(css)
        all_selectors = []

        for rule in rules:
            all_selectors += self.findRuleSelectors(rule)

        # remove pseudoClasses from selectors
        selectors = []
        for sel in all_selectors:
            selectors.append(self.filterPseudo(sel))

        # unique selectors to match on HTML
        selectors = sorted(list(set(selectors)))

        # pprint.pprint(selectors)
        # exit()
        # print "Total selectors found: %d" % len(selectors)
        return selectors

    def findUnusedSelectors(self, html, selectors):
        # log.info("Total selectors to verify: %d" % len(selectors))

        d = pq(html)
        unUsed = []
        for sel in selectors:
            elements = d(sel)
            if not elements:
                unUsed.append(sel)

                # log.info('Total unused selectors to be removed: %d' % len(unUsed))
        # pprint.pprint(unUsed)
        # exit()
        return unUsed

    def isCssValid(self, css):
        # check if css if valid
        rules = tinycss2.parse_stylesheet(css)
        for r in rules:
            if r.type == 'error': return False
        return True

    def removeUnusedSelectorsFromRule(self, rule, unUsed):

        newCss = ''

        # ignore @media queries
        if rule.type == 'at-rule' and rule.lower_at_keyword == 'media':

            # newCss += rule.serialize()
            ruleList = tinycss2.parse_rule_list(rule.content)
            newCss = ''
            for r in ruleList:
                # recursion to deal with @media elements
                css = self.removeUnusedSelectorsFromRule(r, unUsed)
                newCss += css
                if 0:
                    log.debug('BEFORE')
                    log.debug(r.serialize())
                    log.debug('AFTER')
                    log.debug(css)

            # reconstruct media CSS if any rule is left inside @media
            if newCss:
                mediaCss = '@media'
                for node in rule.prelude:
                    mediaCss += node.serialize()
                    # log.debug(node.serialize())

                mediaCss = mediaCss + '{' + newCss + '}'

                if 'fluid' in mediaCss:
                    log.debug("\nMEDIA BEFORE:")
                    log.debug(rule.serialize())
                    log.debug("\nMEDIA AFTER:")
                    log.debug(mediaCss)

                return mediaCss
            else:
                return ''

        # check if there are any used selectors
        ruleCss = rule.serialize()
        selectors = self.getAllCssSelectors(ruleCss)
        selectorsLeft = selectors[:]

        for sel in selectors:
            if sel in unUsed:

                if 'list-style' in ruleCss:
                    log.debug('ANTES')
                    log.debug(ruleCss)

                selectorsLeft.remove(sel)

                if 'list-style' in ruleCss: log.debug(ruleCss)

                # .nav,.sidebar li,.thumbnails{list-style:none}
                # remove class: .thumbnails
                ruleCss = ruleCss.replace(',' + sel + '{', '{')
                if 'list-style' in ruleCss: log.debug(ruleCss)
                # remove class: .sidebar li or .nav
                ruleCss = ruleCss.replace(sel + ',', '')
                if 'list-style' in ruleCss: log.debug(ruleCss)
                # remove class: .nav{
                ruleCss = ruleCss.replace(sel + '{', '{')
                if 'list-style' in ruleCss: log.debug(ruleCss)

                if 'list-style' in ruleCss:
                    log.debug('DEPOIS')
                    log.debug(ruleCss)

        # if any selector left... uses the remaining css
        if selectorsLeft:
            if self.isCssValid(ruleCss):
                newCss += ruleCss
            else:
                log.error('Invalid CSS rule detected after removing unused classes!')
                log.error(ruleCss)
                exit()

        return newCss

    def removeUnusedSelectors(self, css, unUsed):
        # log.info('Removing %d unused selectors from css' % len(unUsed))

        newCss = ''
        rules = tinycss2.parse_stylesheet(css)

        for rule in rules[:]:
            ruleCss = self.removeUnusedSelectorsFromRule(rule, unUsed)
            newCss += ruleCss

        outputCssFile = self.cssPurifiedDir + self.baseFileName + '.css'
        # self.printStats('Unused selectors remotion',css, newCss)

        newCss = newCss.encode('utf8')
        outputCssFile = self.cssOptimizedDir + self.baseFileName + '.css'

        # open(outputCssFile,'w+').write(newCss)

        return newCss

    def inlineCss(self, header, html, css, outputFile):
        if not css: return
        outputFile = outputFile.replace('000_cache_download', '060_cache_upload')

        # remove link to css file
        # <link rel='stylesheet' id='css_comb-css' href='//testes.dowordpress.com.br/wp-content/themes/base/library/css/TDW/all_12022017_1225.css' type='text/css' media='all'/>
        pat = r"<link[^>]*\.css[^>]*>"
        css_link = re.search(pat, html).group(0)
        html = html.replace(css_link, '')

        html = html.replace('</head>', '<style>' + css + '</style>')
        html = html.replace('</style><style>', '')

        html = html.replace('___adsense_CSS_here___', '')

        html = html.split('</html>')[0] + '</html>'

        html += self.optimizedMark

        cacheContent = header + self.cacheHeaderSeparator + html

        open(outputFile, 'w').write(cacheContent)

        return html

    def printStats(self, msg, bef, aft, onlyReturn=0):
        percent = 0
        dif_str = 'no change'

        bef = float(len(bef))
        aft = float(len(aft))

        dif = aft - bef
        if bef > 0:
            percent = dif / bef
            percent *= 100
            percent = abs(percent)

        if aft < bef:
            dif_str = 'decrease'

        if aft > bef:
            dif_str = 'increase'

        msg = '%s : %d -> %d | %.2f %% %s in size' % (msg, bef, aft, percent, dif_str)

        if onlyReturn:
            return msg
        else:
            log.info(msg)


# command line for testing
# python clear_css.py -r testes_dowordpress@testes.dowordpress.com.br:/home/testes_dowordpress/testes.dowordpress.com.br/wp-content/cache/ -o /media/sf_C_DRIVE/Temp/clean_css/


parser = argparse.ArgumentParser(description="Removes unused classes from CSS!", epilog="Yes... lots of improvements")
parser.add_argument("-d", "--debug", action="store_true")
parser.add_argument("-r", "--remoteCachePath", nargs="+", help="Remote cache path to use with rsync")
parser.add_argument("-o", "--outputDir", nargs="+", help="Base directory to save download and optimized files")
parser.add_argument("-i", "--ignoreTemplate", nargs="*",
                    help="HTML file with to force selectors to be ignored. Will be added to HTML when lookink for selectors.")
args = parser.parse_args()

# configure logging
log = logging.getLogger()
log.addHandler(logging.StreamHandler())
log.setLevel(logging.INFO)
if args.debug:
    log.setLevel(logging.DEBUG)

outputDir = args.outputDir[0]
remoteCachePath = args.remoteCachePath[0]

ignoreTemplate = ''
if args.ignoreTemplate:
    ignoreTemplate = args.ignoreTemplate[0]

cCss = clearCss(outputDir, remoteCachePath, ignoreTemplate)

# example command line
# python clear_css.py -d -o /tmp/cache_optimize/MEL/ -r mundodaeletrica@mundodaeletrica.com.br:/home/mundodaeletrica/mundodaeletrica.com.br/wp-content/cache/