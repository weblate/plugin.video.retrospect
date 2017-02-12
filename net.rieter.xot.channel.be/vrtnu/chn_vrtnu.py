import chn_class
import mediaitem
from regexer import Regexer
from parserdata import ParserData
from logger import Logger
from urihandler import UriHandler
from helpers.htmlentityhelper import HtmlEntityHelper
from helpers.jsonhelper import JsonHelper
from streams.m3u8 import M3u8
from vault import Vault
from helpers.datehelper import DateHelper


class Channel(chn_class.Channel):
    """
    main class from which all channels inherit
    """

    def __init__(self, channelInfo):
        """Initialisation of the class.

        Arguments:
        channelInfo: ChannelInfo - The channel info object to base this channel on.

        All class variables should be instantiated here and this method should not
        be overridden by any derived classes.

        """

        chn_class.Channel.__init__(self, channelInfo)

        # ============== Actual channel setup STARTS here and should be overwritten from derived classes ===============
        self.noImage = "vrtnuimage.png"
        self.mainListUri = "https://www.vrt.be/vrtnu/a-z/"
        self.baseUrl = "https://www.vrt.be"

        episodeRegex = '<a[^>]+href="(?<url>/vrtnu[^"]+)"[^>]*>(?:\W*<div[^>]*>\W*){2}' \
                       '<picture[^>]*>\W+<source[^>]+srcset="(?<thumburl>[^ ]+)[\w\W]{0,2000}?' \
                       '<h3[^>]+>(?<title>[^<]+)<span[^>]+>&lt;p&gt;(?<description>[^<]+)' \
                       '&lt;/p&gt;<'
        episodeRegex = Regexer.FromExpresso(episodeRegex)
        self._AddDataParser(self.mainListUri, name="Main A-Z listing",
                            preprocessor=self.AddCategories,
                            matchType=ParserData.MatchExact,
                            parser=episodeRegex, creator=self.CreateEpisodeItem)

        self._AddDataParser("https://search.vrt.be/suggest?facets[categories]",
                            name="JSON Show Parser", json=True,
                            parser=(), creator=self.CreateShowItem)

        self._AddDataParser("https://services.vrt.be/videoplayer/r/live.json", json=True,
                            name="Live streams parser",
                            parser=(), creator=self.CreateLiveStream)
        self._AddDataParser("http://live.stream.vrt.be/",
                            name="Live streams updater",
                            updater=self.UpdateLiveVideo)

        catregex = '<a[^>]+href="(?<url>/vrtnu/categorieen/(?<catid>[^"]+)/)"[^>]*>(?:\W*<div[^>]' \
                   '*>\W*){2}<picture[^>]*>\W+<source[^>]+srcset="(?<thumburl>[^ ]+)' \
                   '[\w\W]{0,2000}?<h3[^>]+>(?<title>[^<]+)'
        catregex = Regexer.FromExpresso(catregex)
        self._AddDataParser("https://www.vrt.be/vrtnu/categorieen/", name="Category parser",
                            matchType=ParserData.MatchExact,
                            parser=catregex,
                            creator=self.CreateCategory)

        folderRegex = '<option[^>]+data-href="/(?<url>[^"]+)">(?<title>[^<]+)</option>'
        folderRegex = Regexer.FromExpresso(folderRegex)
        self._AddDataParser("*", name="Folder/Season parser",
                            parser=folderRegex, creator=self.CreateFolderItem)

        videoRegex = '<a[^>]+href="(?<url>/vrtnu[^"]+)"[^>]*>(?:\W*<div[^>]*>\W*){2}' \
                     '<picture[^>]*>\W+<source[^>]+srcset="(?<thumburl>[^ ]+)[^>]*>\W*' \
                     '<img[^>]+>\W*(?:</\w+>\W*)+<div[^>]+>\W*<h3[^>]+>(?<title>[^<]+)</h3>' \
                     '[\w\W]{0,1000}?(?:<span[^>]+class="tile__broadcastdate--mobile[^>]*>' \
                     '(?<day>\d+)/(?<month>\d+)/?(?<year>\d+)?</span><span[^>]+' \
                     'tile__broadcastdate--other[^>]+>(?<subtitle_>[^<]+)</span></div>\W*<div>)?' \
                     '[^<]*<abbr[^>]+title'
        # No need for a subtitle for now as it only includes the textual date
        videoRegex = Regexer.FromExpresso(videoRegex)
        self._AddDataParser("*", name="Video item parser",
                            parser=videoRegex, creator=self.CreateVideoItem)

        # needs to be after the standard video item regex
        singleVideoRegex = '<picture[^>]*>\W+<source[^>]+srcset="(?<thumburl>[^ ]+)[\w\W]{0,4000}' \
                           '<span[^>]+id="title"[^>]*>(?<title>[^<]+)</span>\W*<span[^>]+>' \
                           '(?<description>[^<]+)'
        singleVideoRegex = Regexer.FromExpresso(singleVideoRegex)
        self._AddDataParser("*", name="Single video item parser",
                            parser=singleVideoRegex, creator=self.CreateVideoItem)

        self._AddDataParser("*", updater=self.UpdateVideoItem, requiresLogon=True)

        # ===============================================================================================================
        # non standard items
        self.__hasAlreadyVideoItems = False

        # ===============================================================================================================
        # Test cases:

        # ====================================== Actual channel setup STOPS here =======================================
        return

    def LogOn(self):
        tokenCookie = UriHandler.GetCookie("X-VRT-Token", ".vrt.be")
        if tokenCookie is not None:
            return True

        username = self._GetSetting("username")
        if not username:
            return None

        v = Vault()
        password = v.GetChannelSetting(self.guid, "password")

        Logger.Debug("Using: %s / %s", username, "*" * len(password))
        url = "https://accounts.eu1.gigya.com/accounts.login"
        data = "loginID=%s" \
               "&password=%s" \
               "&targetEnv=jssdk" \
               "&APIKey=3_qhEcPa5JGFROVwu5SWKqJ4mVOIkwlFNMSKwzPDAh8QZOtHqu6L4nD5Q7lk0eXOOG" \
               "&includeSSOToken=true" \
               "&authMode=cookie" % \
               (HtmlEntityHelper.UrlEncode(username), HtmlEntityHelper.UrlEncode(password))

        logonData = UriHandler.Open(url, params=data, proxy=self.proxy, noCache=True)
        sig, uid, timestamp = self.__ExtractSessionData(logonData)
        url = "https://token.vrt.be/"
        tokenData = '{"uid": "%s", ' \
                    '"uidsig": "%s", ' \
                    '"ts": "%s", ' \
                    '"fn": "VRT", "ln": "NU", ' \
                    '"email": "%s"}' % (uid, sig, timestamp, username)

        headers = {"Content-Type": "application/json", "Referer": "https://www.vrt.be/vrtnu/"}
        UriHandler.Open(url, params=tokenData, proxy=self.proxy, additionalHeaders=headers)
        return True

    def AddCategories(self, data):
        Logger.Info("Performing Pre-Processing")
        items = []

        cat = mediaitem.MediaItem("\a.: Categori&euml;n :.", "https://www.vrt.be/vrtnu/categorieen/")
        cat.fanart = self.fanart
        cat.thumb = self.noImage
        cat.icon = self.icon
        cat.dontGroup = True
        items.append(cat)

        live = mediaitem.MediaItem("\a.: Live Streams :.", "https://services.vrt.be/videoplayer/r/live.json")
        live.fanart = self.fanart
        live.thumb = self.noImage
        live.icon = self.icon
        live.dontGroup = True
        live.isLive = True
        items.append(live)

        Logger.Debug("Pre-Processing finished")
        return data, items

    def CreateCategory(self, resultSet):
        # https://search.vrt.be/suggest?facets[categories]=met-audiodescriptie
        resultSet["url"] = "https://search.vrt.be/suggest?facets[categories]=%(catid)s" % resultSet
        item = chn_class.Channel.CreateFolderItem(self, resultSet)
        if item is not None and item.thumb and item.thumb.startswith("//"):
            item.thumb = "https:%s" % (item.thumb, )

        return item

    def CreateLiveStream(self, resultSet):
        items = []
        for keyValue, streamValue in resultSet.iteritems():
            Logger.Trace(streamValue)

            # stuff taken from: http://radioplus.be/conf/channels.js
            # fanart = self.parentItem.fanart
            # thumb = self.parentItem.thumb
            if keyValue == "mnm":
                title = "MNM"
                fanart = "http://radioplus.be/img/channels/mnm/splash@2x.jpg"
                # thumb = "http://radioplus.be/img/channels/mnm/logo@2x.png"
                thumb = "http://radioplus.be/img/channels/mnm/thumb@2x.jpg"
            elif keyValue == "stubru":
                title = "Studio Brussel"
                fanart = "http://radioplus.be/img/channels/stubru/splash@2x.jpg"
                # thumb = "http://radioplus.be/img/channels/stubru/logo@2x.png"
                thumb = "http://radioplus.be/img/channels/stubru/thumb@2x.jpg"
            elif keyValue == "vrtvideo1":
                title = "E&eacute;n"
                fanart = "http://cdn.rieter.net/net.rieter.xot.cdn/net.rieter.xot.channel.be.een/eenfanart.jpg"
                thumb = "http://cdn.rieter.net/net.rieter.xot.cdn/net.rieter.xot.channel.be.een/eenimage.png"
            elif keyValue == "vrtvideo2":
                title = "Canvas"
                fanart = "http://cdn.rieter.net/net.rieter.xot.cdn/net.rieter.xot.channel.be.canvas/canvasfanart.png"
                thumb = "http://cdn.rieter.net/net.rieter.xot.cdn/net.rieter.xot.channel.be.canvas/canvasimage.png"
            elif keyValue == "events3":
                title = "Ketnet"
                fanart = "http://cdn.rieter.net/net.rieter.xot.cdn/net.rieter.xot.channel.be.ketnet/ketnetfanart.jpg"
                thumb = "http://cdn.rieter.net/net.rieter.xot.cdn/net.rieter.xot.channel.be.ketnet/ketnetimage.png"
            elif keyValue == "sporza":
                title = "Sporza"
                fanart = "http://cdn.rieter.net/net.rieter.xot.cdn/net.rieter.xot.channel.be.sporza/sportzafanart.jpg"
                thumb = "http://cdn.rieter.net/net.rieter.xot.cdn/net.rieter.xot.channel.be.sporza/sporzaimage.png"
            else:
                continue

            liveItem = mediaitem.MediaItem(title, streamValue["hls"])
            liveItem.isLive = True
            liveItem.type = 'video'
            liveItem.fanart = fanart
            liveItem.thumb = thumb
            items.append(liveItem)

        return items

    def CreateShowItem(self, resultSet):
        Logger.Trace(resultSet)
        if resultSet["targetUrl"].startswith("//"):
            resultSet["url"] = "https:%(targetUrl)s" % resultSet
        else:
            resultSet["url"] = resultSet["targetUrl"]
        resultSet["thumburl"] = resultSet["thumbnail"]

        return chn_class.Channel.CreateEpisodeItem(self, resultSet)

    def CreateEpisodeItem(self, resultSet):
        item = chn_class.Channel.CreateEpisodeItem(self, resultSet)

        if item is not None and item.thumb and item.thumb.startswith("//"):
            item.thumb = "https:%s" % (item.thumb, )

        return item

    def CreateFolderItem(self, resultSet):
        item = chn_class.Channel.CreateFolderItem(self, resultSet)
        if item is None:
            return None

        item.name = item.name.title()
        return item

    def CreateVideoItem(self, resultSet):
        resultSet["title"] = resultSet["title"].strip()
        if "url" not in resultSet:
            if self.__hasAlreadyVideoItems:
                Logger.Debug("Found a 'single' item, but we have more. So this is a duplicate")
                return None

            # this only happens once with single video folders
            resultSet["url"] = self.parentItem.url

        item = chn_class.Channel.CreateVideoItem(self, resultSet)
        if item is None:
            return None

        if "day" in resultSet and resultSet["day"]:
            item.SetDate(resultSet["year"] or DateHelper.ThisYear(), resultSet["month"], resultSet["day"])

        if item.thumb.startswith("//"):
            item.thumb = "https:%s" % (item.thumb, )

        self.__hasAlreadyVideoItems = True
        return item

    def UpdateLiveVideo(self, item):
        if "m3u8" not in item.url:
            Logger.Error("Cannot update live stream that is not an M3u8: %s", item.url)

        part = item.CreateNewEmptyMediaPart()
        for s, b in M3u8.GetStreamsFromM3u8(item.url, self.proxy):
            item.complete = True
            # s = self.GetVerifiableVideoUrl(s)
            part.AppendMediaStream(s, b)
        return item

    def UpdateVideoItem(self, item):
        Logger.Debug('Starting UpdateVideoItem for %s (%s)', item.name, self.channelName)

        # we need to fetch the actual url as it might differ for single video items
        data, secureUrl = UriHandler.Header(item.url, proxy=self.proxy)

        secureUrl = secureUrl.rstrip("/")
        secureUrl = "%s.securevideo.json" % (secureUrl, )
        data = UriHandler.Open(secureUrl, proxy=self.proxy, additionalHeaders=item.HttpHeaders)
        secureData = JsonHelper(data, logger=Logger.Instance())
        mzid = secureData.GetValue(secureData.json.keys()[0], "mzid")
        assetUrl = "https://mediazone.vrt.be/api/v1/vrtvideo/assets/%s" % (mzid, )
        data = UriHandler.Open(assetUrl, proxy=self.proxy)
        assetData = JsonHelper(data, logger=Logger.Instance())

        for streamData in assetData.GetValue("targetUrls"):
            if streamData["type"] != "HLS":
                continue

            part = item.CreateNewEmptyMediaPart()
            for s, b in M3u8.GetStreamsFromM3u8(streamData["url"], self.proxy):
                item.complete = True
                # s = self.GetVerifiableVideoUrl(s)
                part.AppendMediaStream(s, b)
        return item

    def __ExtractSessionData(self, logonData):
        logonJson = JsonHelper(logonData)
        resultCode = logonJson.GetValue("statusCode")
        if resultCode != 200:
            Logger.Error("Error loging in: %s - %s", logonJson.GetValue("errorMessage"),
                         logonJson.GetValue("errorDetails"))
            return False

        return \
            logonJson.GetValue("UIDSignature"), \
            logonJson.GetValue("UID"), \
            logonJson.GetValue("signatureTimestamp")