(function () {
  var canvas = document.getElementById('poster-canvas');
  var dataNode = document.getElementById('poster-data');
  if (!canvas || !dataNode) return;

  var ctx = canvas.getContext('2d');
  var W = canvas.width;
  var H = canvas.height;
  var posterData = JSON.parse(dataNode.textContent);
  var bg = new Image();
  var customBg = null;
  var customBgUrl = '';
  var bgSettings = {
    x: 0,
    y: 0,
    zoom: 1,
    opacity: 1,
  };
  var maskSettings = {
    mode: 'default',
    color: '#071426',
    angle: 325,
    maxOpacity: 1,
    minOpacity: 0.5,
    curve: 'power',
  };
  var chartSettings = {
    mode: posterData.chartMode === 'log' ? 'log' : 'default',
  };

  var palette = {
    navy: '#071426',
    panel: 'rgba(7, 15, 32, 0.52)',
    panelStrong: 'rgba(8, 17, 38, 0.72)',
    border: 'rgba(255, 255, 255, 0.18)',
    gold: '#f7c84b',
    goldSoft: 'rgba(247, 200, 75, 0.24)',
    red: '#ff416d',
    redDark: '#a81735',
    danger: '#ff344f',
    text: '#f8fbff',
    muted: 'rgba(226, 236, 255, 0.68)',
    grid: 'rgba(255, 255, 255, 0.10)',
  };

  var titleStyles = {
    '赌怪': { color: '#ff3f7f', size: 24, glow: 'rgba(255, 63, 127, 0.72)' },
    '赌王': { color: '#f7c84b', size: 22, glow: 'rgba(247, 200, 75, 0.58)' },
    '赌狗': { color: '#6ee7f9', size: 20, glow: 'rgba(110, 231, 249, 0.46)' },
    '费马': { color: 'rgba(226, 236, 255, 0.72)', size: 18, glow: 'rgba(226, 236, 255, 0.24)' },
  };

  bg.crossOrigin = 'anonymous';
  bg.onload = drawPoster;
  bg.onerror = drawPoster;
  bg.src = 'https://i1.hdslb.com/bfs/new_dyn/a646cb7f5af320998220e541076f6bc9390644905.png@1052w_!web-dynamic.avif';

  function font(weight, size) {
    return weight + ' ' + size + 'px "Microsoft YaHei", "PingFang SC", Arial, sans-serif';
  }

  function formatAmount(value) {
    var numeric = Math.round(Number(value) || 0);
    var sign = numeric < 0 ? '-' : '';
    var absolute = Math.abs(numeric).toString();
    return sign + absolute.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  function formatDate(value) {
    var d = new Date(value);
    if (Number.isNaN(d.getTime())) return '';
    return (d.getMonth() + 1) + '/' + d.getDate();
  }

  function roundRect(x, y, w, h, r) {
    var radius = Math.min(r, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.arcTo(x + w, y, x + w, y + h, radius);
    ctx.arcTo(x + w, y + h, x, y + h, radius);
    ctx.arcTo(x, y + h, x, y, radius);
    ctx.arcTo(x, y, x + w, y, radius);
    ctx.closePath();
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function componentToHex(value) {
    return clamp(Math.round(value) || 0, 0, 255).toString(16).padStart(2, '0');
  }

  function rgbToHex(rgb) {
    return '#' + componentToHex(rgb[0]) + componentToHex(rgb[1]) + componentToHex(rgb[2]);
  }

  function hexToRgb(hex) {
    var value = String(hex || '').trim().replace(/^#/, '');
    if (value.length === 3) {
      value = value.split('').map(function (ch) { return ch + ch; }).join('');
    }
    if (!/^[0-9a-fA-F]{6}$/.test(value)) return [7, 20, 38];
    return [
      parseInt(value.slice(0, 2), 16),
      parseInt(value.slice(2, 4), 16),
      parseInt(value.slice(4, 6), 16),
    ];
  }

  function rgbaFromHex(hex, opacity) {
    var rgb = hexToRgb(hex);
    return 'rgba(' + rgb[0] + ', ' + rgb[1] + ', ' + rgb[2] + ', ' + clamp(opacity, 0, 1).toFixed(3) + ')';
  }

  function colorDistance(a, b) {
    var dr = a[0] - b[0];
    var dg = a[1] - b[1];
    var db = a[2] - b[2];
    return Math.sqrt(dr * dr + dg * dg + db * db);
  }

  function saturation(rgb) {
    var r = rgb[0] / 255;
    var g = rgb[1] / 255;
    var b = rgb[2] / 255;
    var mx = Math.max(r, g, b);
    var mn = Math.min(r, g, b);
    return mx === 0 ? 0 : (mx - mn) / mx;
  }

  function brightness(rgb) {
    return Math.max(rgb[0], rgb[1], rgb[2]) / 255;
  }

  function extractDominantColor(image, done) {
    if (!image || !image.naturalWidth || !image.naturalHeight) return;
    var maxSide = 300;
    var scale = Math.min(1, maxSide / Math.max(image.naturalWidth, image.naturalHeight));
    var w = Math.max(1, Math.round(image.naturalWidth * scale));
    var h = Math.max(1, Math.round(image.naturalHeight * scale));
    var sampleCanvas = document.createElement('canvas');
    sampleCanvas.width = w;
    sampleCanvas.height = h;
    var sampleCtx = sampleCanvas.getContext('2d', { willReadFrequently: true });
    sampleCtx.drawImage(image, 0, 0, w, h);
    var data;
    try {
      data = sampleCtx.getImageData(0, 0, w, h).data;
    } catch (err) {
      return;
    }

    var pixels = [];
    var pixelCount = data.length / 4;
    var step = Math.max(1, Math.floor(pixelCount / 12000));
    for (var i = 0; i < pixelCount; i += step) {
      var offset = i * 4;
      if (data[offset + 3] < 32) continue;
      pixels.push([data[offset], data[offset + 1], data[offset + 2]]);
    }
    if (!pixels.length) return;

    var k = Math.min(5, pixels.length);
    var centers = [];
    for (var c = 0; c < k; c++) {
      centers.push(pixels[Math.floor((pixels.length - 1) * (c + 0.5) / k)].slice());
    }

    var labels = new Array(pixels.length);
    for (var iter = 0; iter < 8; iter++) {
      var sums = [];
      var counts = [];
      for (var s = 0; s < k; s++) {
        sums.push([0, 0, 0]);
        counts.push(0);
      }
      for (var p = 0; p < pixels.length; p++) {
        var bestIndex = 0;
        var bestDistance = Infinity;
        for (var ci = 0; ci < k; ci++) {
          var dist = colorDistance(pixels[p], centers[ci]);
          if (dist < bestDistance) {
            bestDistance = dist;
            bestIndex = ci;
          }
        }
        labels[p] = bestIndex;
        sums[bestIndex][0] += pixels[p][0];
        sums[bestIndex][1] += pixels[p][1];
        sums[bestIndex][2] += pixels[p][2];
        counts[bestIndex] += 1;
      }
      for (var u = 0; u < k; u++) {
        if (!counts[u]) continue;
        centers[u] = [
          sums[u][0] / counts[u],
          sums[u][1] / counts[u],
          sums[u][2] / counts[u],
        ];
      }
    }

    var centerCounts = new Array(k).fill(0);
    labels.forEach(function (label) { centerCounts[label] += 1; });
    var used = new Array(k).fill(false);
    var merged = [];
    for (var m = 0; m < k; m++) {
      if (used[m]) continue;
      var countSum = centerCounts[m];
      var colorSum = [
        centers[m][0] * centerCounts[m],
        centers[m][1] * centerCounts[m],
        centers[m][2] * centerCounts[m],
      ];
      used[m] = true;
      for (var n = m + 1; n < k; n++) {
        if (used[n] || colorDistance(centers[m], centers[n]) >= 40) continue;
        colorSum[0] += centers[n][0] * centerCounts[n];
        colorSum[1] += centers[n][1] * centerCounts[n];
        colorSum[2] += centers[n][2] * centerCounts[n];
        countSum += centerCounts[n];
        used[n] = true;
      }
      if (!countSum) continue;
      merged.push({
        color: [colorSum[0] / countSum, colorSum[1] / countSum, colorSum[2] / countSum],
        count: countSum,
      });
    }
    if (!merged.length) return;

    var best = null;
    var fallback = merged[0];
    merged.forEach(function (item) {
      if (item.count > fallback.count) fallback = item;
      var sat = saturation(item.color);
      var bright = brightness(item.color);
      if (bright > 0.93 || bright < 0.05 || sat < 0.08) return;
      var areaRatio = item.count / pixels.length;
      var brightnessScore = 1 - Math.abs(bright - 0.55) * 2;
      var score = 0.60 * areaRatio + 0.25 * sat + 0.15 * Math.max(0, brightnessScore);
      if (!best || score > best.score) best = { color: item.color, score: score };
    });
    var result = (best || fallback).color.map(function (value) { return Math.round(value); });
    done(rgbToHex(result));
  }

  function drawCoverImage(image, x, y, w, h, settings) {
    if (!image || !image.naturalWidth || !image.naturalHeight) return false;
    var imageRatio = image.naturalWidth / image.naturalHeight;
    var boxRatio = w / h;
    var sw = image.naturalWidth;
    var sh = image.naturalHeight;
    var sx = 0;
    var sy = 0;
    if (imageRatio > boxRatio) {
      sw = sh * boxRatio;
      sx = (image.naturalWidth - sw) / 2;
    } else {
      sh = sw / boxRatio;
      sy = (image.naturalHeight - sh) / 2;
    }
    if (settings) {
      var zoom = Math.max(1, Number(settings.zoom) || 1);
      sw = sw / zoom;
      sh = sh / zoom;
      var maxSx = Math.max(0, image.naturalWidth - sw);
      var maxSy = Math.max(0, image.naturalHeight - sh);
      sx = clamp((image.naturalWidth - sw) / 2 + (Number(settings.x) || 0) * maxSx / 2, 0, maxSx);
      sy = clamp((image.naturalHeight - sh) / 2 + (Number(settings.y) || 0) * maxSy / 2, 0, maxSy);
    }
    ctx.drawImage(image, sx, sy, sw, sh, x, y, w, h);
    return true;
  }

  function drawBackground() {
    var activeBg = customBg && customBg.naturalWidth ? customBg : bg;
    var cropSettings = activeBg === customBg ? bgSettings : null;
    var opacity = activeBg === customBg ? clamp(Number(bgSettings.opacity) || 0, 0, 1) : 1;
    var loaded = false;
    if (activeBg && activeBg.naturalWidth) {
      ctx.save();
      ctx.globalAlpha = opacity;
      loaded = drawCoverImage(activeBg, 0, 0, W, H, cropSettings);
      ctx.restore();
    }
    if (!loaded) {
      var fallback = ctx.createLinearGradient(0, 0, W, H);
      fallback.addColorStop(0, '#10223e');
      fallback.addColorStop(0.52, '#061326');
      fallback.addColorStop(1, '#0d0b16');
      ctx.fillStyle = fallback;
      ctx.fillRect(0, 0, W, H);
    } else {
      ctx.save();
      ctx.globalAlpha = 0.36 * opacity;
      ctx.filter = 'blur(18px) saturate(1.08)';
      drawCoverImage(activeBg, -18, -18, W + 36, H + 36, cropSettings);
      ctx.restore();
    }

    if (maskSettings.mode === 'custom') {
      drawCustomMask();
      return;
    }

    var veil = ctx.createLinearGradient(0, 0, W, H);
    veil.addColorStop(0, 'rgba(5, 14, 31, 0.46)');
    veil.addColorStop(0.34, 'rgba(4, 11, 24, 0.66)');
    veil.addColorStop(0.66, 'rgba(5, 13, 31, 0.76)');
    veil.addColorStop(1, 'rgba(3, 8, 19, 0.84)');
    ctx.fillStyle = veil;
    ctx.fillRect(0, 0, W, H);

    var frost = ctx.createLinearGradient(0, 0, 0, H);
    frost.addColorStop(0, 'rgba(255, 255, 255, 0.13)');
    frost.addColorStop(0.28, 'rgba(255, 255, 255, 0.04)');
    frost.addColorStop(0.72, 'rgba(255, 255, 255, 0.02)');
    frost.addColorStop(1, 'rgba(255, 255, 255, 0.08)');
    ctx.fillStyle = frost;
    ctx.fillRect(0, 0, W, H);

    var spotlight = ctx.createRadialGradient(1010, 88, 0, 1010, 88, 560);
    spotlight.addColorStop(0, 'rgba(247, 200, 75, 0.20)');
    spotlight.addColorStop(0.48, 'rgba(247, 200, 75, 0.05)');
    spotlight.addColorStop(1, 'rgba(247, 200, 75, 0)');
    ctx.fillStyle = spotlight;
    ctx.fillRect(0, 0, W, H);
  }

  function customMaskCurve(t, curve) {
    var x = clamp(t, 0, 1);
    if (curve === 's') return x * x * x * (x * (x * 6 - 15) + 10);
    if (curve === 'exponential') return (Math.exp(3 * x) - 1) / (Math.exp(3) - 1);
    if (curve === 'power') return x * x;
    return x;
  }

  function drawCustomMask() {
    var high = clamp(Number(maskSettings.maxOpacity), 0, 1);
    var low = clamp(Number(maskSettings.minOpacity), 0, 1);
    if (low > high) {
      var temp = high;
      high = low;
      low = temp;
    }
    var angle = (Number(maskSettings.angle) || 0) * Math.PI / 180;
    var radius = Math.sqrt(W * W + H * H) / 2;
    var dx = Math.cos(angle) * radius;
    var dy = Math.sin(angle) * radius;
    var gradient = ctx.createLinearGradient(W / 2 - dx, H / 2 - dy, W / 2 + dx, H / 2 + dy);
    var steps = 16;
    for (var i = 0; i <= steps; i++) {
      var t = i / steps;
      var opacity = high + (low - high) * customMaskCurve(t, maskSettings.curve);
      gradient.addColorStop(t, rgbaFromHex(maskSettings.color, opacity));
    }
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, W, H);
  }

  function drawGlassCard(x, y, w, h, radius, options) {
    var opts = options || {};
    ctx.save();
    ctx.shadowColor = opts.shadow || 'rgba(0, 0, 0, 0.34)';
    ctx.shadowBlur = opts.blur || 26;
    ctx.shadowOffsetY = opts.offsetY || 14;
    roundRect(x, y, w, h, radius);
    ctx.fillStyle = opts.fill || palette.panel;
    ctx.fill();
    ctx.shadowBlur = 0;
    ctx.shadowOffsetY = 0;
    ctx.strokeStyle = opts.border || palette.border;
    ctx.lineWidth = 1;
    ctx.stroke();

    var shine = ctx.createLinearGradient(x, y, x, y + h);
    shine.addColorStop(0, 'rgba(255, 255, 255, 0.16)');
    shine.addColorStop(0.22, 'rgba(255, 255, 255, 0.04)');
    shine.addColorStop(1, 'rgba(255, 255, 255, 0)');
    roundRect(x + 1, y + 1, w - 2, h - 2, Math.max(0, radius - 1));
    ctx.fillStyle = shine;
    ctx.fill();
    ctx.restore();
  }

  function drawFittedText(text, x, y, maxWidth, weight, size, minSize, align, color) {
    var fontSize = size;
    ctx.textAlign = align || 'left';
    ctx.textBaseline = 'top';
    ctx.fillStyle = color || palette.text;
    do {
      ctx.font = font(weight, fontSize);
      if (ctx.measureText(text).width <= maxWidth || fontSize <= minSize) break;
      fontSize -= 1;
    } while (fontSize > minSize);
    ctx.fillText(text, x, y);
    return fontSize;
  }

  function playerTitle(rank, totalPlayers) {
    var total = Math.max(1, Number(totalPlayers) || 1);
    var topPercent = Math.max(0, Math.min(100, (Number(rank) || total) / total * 100));
    if (topPercent <= 10) return '赌怪';
    if (topPercent <= 30) return '赌王';
    if (topPercent <= 50) return '赌狗';
    return '费马';
  }

  function drawHeader(currentAmount, coinName, nickname, titleName) {
    ctx.save();
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillStyle = palette.gold;
    ctx.font = font('700', 13);
    ctx.fillText('FERMAT COIN SEASON RECAP', 48, 32);

    ctx.shadowColor = 'rgba(0, 0, 0, 0.48)';
    ctx.shadowBlur = 18;
    var titleStyle = titleStyles[titleName] || titleStyles['费马'];
    var nameSize = drawFittedText(nickname, 48, 51, 274, '800', 42, 26, 'left', palette.text);
    var nameWidth = Math.min(274, ctx.measureText(nickname).width);
    var titleX = 62 + nameWidth;
    var titleY = 57 + Math.max(0, (nameSize - titleStyle.size) / 2);
    ctx.font = font('900', titleStyle.size);
    var titleW = ctx.measureText(titleName).width + 24;
    ctx.shadowBlur = 0;
    ctx.beginPath();
    roundRect(titleX - 12, titleY - 5, titleW, titleStyle.size + 13, 6);
    ctx.fillStyle = 'rgba(6, 14, 30, 0.62)';
    ctx.fill();
    ctx.strokeStyle = titleStyle.color;
    ctx.globalAlpha = 0.86;
    ctx.stroke();
    ctx.globalAlpha = 1;
    ctx.shadowColor = titleStyle.glow;
    ctx.shadowBlur = 16;
    ctx.fillStyle = titleStyle.color;
    ctx.fillText(titleName, titleX, titleY);
    ctx.shadowBlur = 0;
    ctx.restore();

    ctx.save();
    ctx.textAlign = 'right';
    ctx.textBaseline = 'top';
    ctx.fillStyle = 'rgba(226, 236, 255, 0.74)';
    ctx.font = font('700', 14);
    ctx.fillText('Current Amount', W - 48, 30);
    ctx.shadowColor = currentAmount < 0 ? 'rgba(255, 65, 109, 0.44)' : 'rgba(247, 200, 75, 0.34)';
    ctx.shadowBlur = 22;
    drawFittedText(formatAmount(currentAmount), W - 48, 51, 500, '900', 56, 34, 'right', palette.text);
    ctx.shadowBlur = 0;
    ctx.fillStyle = palette.gold;
    ctx.font = font('800', 24);
    ctx.fillText(coinName, W - 48, 111);
    ctx.restore();

    var accent = ctx.createLinearGradient(40, 0, W - 40, 0);
    accent.addColorStop(0, 'rgba(247, 200, 75, 0)');
    accent.addColorStop(0.22, 'rgba(247, 200, 75, 0.72)');
    accent.addColorStop(0.72, 'rgba(255, 65, 109, 0.48)');
    accent.addColorStop(1, 'rgba(255, 65, 109, 0)');
    ctx.fillStyle = accent;
    ctx.fillRect(40, 146, W - 80, 2);
  }

  function drawTrophy(x, y, scale) {
    ctx.save();
    ctx.translate(x, y);
    ctx.scale(scale, scale);
    var cup = ctx.createLinearGradient(0, 0, 0, 42);
    cup.addColorStop(0, '#ffe58a');
    cup.addColorStop(0.52, palette.gold);
    cup.addColorStop(1, '#a96f13');
    ctx.fillStyle = cup;
    ctx.beginPath();
    roundRect(9, 5, 30, 26, 5);
    ctx.fill();
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.35)';
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(8, 15, 9, Math.PI * 0.5, Math.PI * 1.55);
    ctx.arc(50, 15, 9, Math.PI * 1.45, Math.PI * 0.5);
    ctx.strokeStyle = palette.gold;
    ctx.lineWidth = 4;
    ctx.stroke();
    ctx.fillStyle = palette.gold;
    ctx.fillRect(22, 31, 5, 10);
    ctx.fillRect(31, 31, 5, 10);
    ctx.beginPath();
    roundRect(15, 41, 28, 7, 3);
    ctx.fill();
    ctx.restore();
  }

  function drawRankBadge(x, y, w, h, rank, totalPlayers) {
    var safeTotal = Math.max(0, Number(totalPlayers) || 0);
    var safeRank = Math.max(0, Number(rank) || 0);
    var rankPercent = safeTotal ? Math.max(0, Math.min(100, (1 - safeRank / safeTotal) * 100)) : 0;
    var topPercent = safeTotal ? Math.max(0, Math.min(100, (safeRank / safeTotal) * 100)) : 0;

    drawTrophy(x + 22, y + 22, 0.78);

    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillStyle = palette.gold;
    ctx.font = font('800', 14);
    ctx.fillText('Rank', x + 78, y + 24);
    drawFittedText('#' + safeRank + ' / ' + safeTotal, x + 78, y + 45, w - 104, '900', 34, 24, 'left', palette.text);

    ctx.fillStyle = palette.muted;
    ctx.font = font('700', 15);
    ctx.fillText('Top ' + topPercent.toFixed(1) + '%', x + 28, y + 104);

    var trackX = x + 28;
    var trackY = y + 136;
    var trackW = w - 56;
    var trackH = 12;
    roundRect(trackX, trackY, trackW, trackH, 6);
    ctx.fillStyle = 'rgba(255, 255, 255, 0.12)';
    ctx.fill();
    var fillW = Math.max(8, trackW * rankPercent / 100);
    var rankGrad = ctx.createLinearGradient(trackX, 0, trackX + trackW, 0);
    rankGrad.addColorStop(0, palette.red);
    rankGrad.addColorStop(0.62, palette.gold);
    rankGrad.addColorStop(1, '#fff1a8');
    roundRect(trackX, trackY, fillW, trackH, 6);
    ctx.fillStyle = rankGrad;
    ctx.fill();

    ctx.fillStyle = 'rgba(226, 236, 255, 0.56)';
    ctx.font = font('600', 12);
    ctx.fillText('Percentile momentum', trackX, trackY + 24);
  }

  function drawMetricCard(x, y, w, h, title, value, accent) {
    ctx.fillStyle = palette.muted;
    ctx.font = font('800', 13);
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText(title, x + 18, y + 15);
    drawFittedText(value, x + 18, y + 39, w - 36, '900', 30, 20, 'left', accent || palette.text);
  }

  function clamp01(value) {
    return Math.max(0, Math.min(1, Number(value) || 0));
  }

  function formatPercent(value) {
    return ((Number(value) || 0) * 100).toFixed(1) + '%';
  }

  function formatOdds(value) {
    return (Number(value) || 0).toFixed(2) + 'x';
  }

  function radarItems(stats) {
    var s = stats || {};
    function raw(key) {
      var item = s[key];
      if (item && typeof item === 'object') return Number(item.value) || 0;
      return Number(item) || 0;
    }
    function score(key) {
      var item = s[key];
      if (item && typeof item === 'object') return clamp01(item.score);
      return 0;
    }
    return [
      {
        label: '胜率',
        value: formatPercent(raw('winRate')),
        score: score('winRate'),
      },
      {
        label: '最高赔率',
        value: formatOdds(raw('maxWinOdds')),
        score: score('maxWinOdds'),
      },
      {
        label: '最大返利',
        value: formatAmount(raw('maxSingleRebate')),
        score: score('maxSingleRebate'),
      },
      {
        label: '平均赔率',
        value: formatOdds(raw('avgWinOdds')),
        score: score('avgWinOdds'),
      },
      {
        label: '平均返利',
        value: formatAmount(raw('avgWinRebate')),
        score: score('avgWinRebate'),
      },
      {
        label: '回报率',
        value: formatPercent(raw('returnRate')),
        score: score('returnRate'),
      },
    ];
  }

  function polygonPoints(cx, cy, radius, count) {
    var points = [];
    for (var i = 0; i < count; i++) {
      var angle = -Math.PI / 2 + Math.PI * 2 * i / count;
      points.push({
        x: cx + Math.cos(angle) * radius,
        y: cy + Math.sin(angle) * radius,
      });
    }
    return points;
  }

  function drawPolygon(points) {
    ctx.beginPath();
    points.forEach(function (point, index) {
      if (index === 0) ctx.moveTo(point.x, point.y);
      else ctx.lineTo(point.x, point.y);
    });
    ctx.closePath();
  }

  function drawRadarChart(x, y, w, h, stats) {
    var items = radarItems(stats);
    var cx = x + w / 2;
    var cy = y + h / 2 + 4;
    var radius = Math.min(w * 0.32, h * 0.36);

    ctx.save();
    for (var level = 4; level >= 1; level--) {
      var gridPoints = polygonPoints(cx, cy, radius * level / 4, items.length);
      drawPolygon(gridPoints);
      ctx.strokeStyle = level === 4 ? 'rgba(247, 200, 75, 0.28)' : 'rgba(255, 255, 255, 0.10)';
      ctx.lineWidth = level === 4 ? 1.3 : 1;
      ctx.stroke();
    }

    var outer = polygonPoints(cx, cy, radius, items.length);
    outer.forEach(function (point) {
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(point.x, point.y);
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.10)';
      ctx.lineWidth = 1;
      ctx.stroke();
    });

    var dataPoints = items.map(function (item, index) {
      var angle = -Math.PI / 2 + Math.PI * 2 * index / items.length;
      var r = radius * Math.max(0.08, item.score);
      return {
        x: cx + Math.cos(angle) * r,
        y: cy + Math.sin(angle) * r,
      };
    });

    var radarFill = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
    radarFill.addColorStop(0, 'rgba(247, 200, 75, 0.36)');
    radarFill.addColorStop(1, 'rgba(255, 65, 109, 0.34)');
    drawPolygon(dataPoints);
    ctx.fillStyle = radarFill;
    ctx.fill();
    ctx.strokeStyle = palette.gold;
    ctx.lineWidth = 2.2;
    ctx.shadowColor = 'rgba(247, 200, 75, 0.36)';
    ctx.shadowBlur = 12;
    ctx.stroke();
    ctx.shadowBlur = 0;

    dataPoints.forEach(function (point) {
      ctx.fillStyle = palette.gold;
      ctx.beginPath();
      ctx.arc(point.x, point.y, 3.6, 0, Math.PI * 2);
      ctx.fill();
    });

    ctx.textBaseline = 'middle';
    items.forEach(function (item, index) {
      var point = outer[index];
      var labelX = point.x + (point.x - cx) * 0.24;
      var labelY = point.y + (point.y - cy) * 0.18;
      ctx.textAlign = labelX < cx - 6 ? 'right' : labelX > cx + 6 ? 'left' : 'center';
      ctx.fillStyle = palette.muted;
      ctx.font = font('800', 11);
      ctx.fillText(item.label, labelX, labelY - 7);
      ctx.fillStyle = palette.text;
      ctx.font = font('900', 11);
      ctx.fillText(item.value, labelX, labelY + 8);
    });
    ctx.restore();
  }

  function pointAt(history, values, index, plot) {
    var denom = Math.max(1, history.length - 1);
    return {
      x: plot.x + (index / denom) * plot.w,
      y: plot.y + plot.h - ((values[index] - plot.yMin) / plot.yRange) * plot.h,
    };
  }

  function chartScaleValue(value, positiveLog) {
    if (chartSettings.mode !== 'log') return value;
    if (positiveLog) return Math.log10(Math.max(value, 1e-9));
    if (value === 0) return 0;
    return (value < 0 ? -1 : 1) * Math.log10(Math.abs(value) + 1);
  }

  function chartUnscaleValue(value, positiveLog) {
    if (chartSettings.mode !== 'log') return value;
    if (positiveLog) return Math.pow(10, value);
    if (value === 0) return 0;
    return (value < 0 ? -1 : 1) * (Math.pow(10, Math.abs(value)) - 1);
  }

  function rectsOverlap(a, b, gap) {
    return !(
      a.x + a.w + gap < b.x ||
      b.x + b.w + gap < a.x ||
      a.y + a.h + gap < b.y ||
      b.y + b.h + gap < a.y
    );
  }

  function placeLabel(px, py, w, h, bounds, preferred, occupied) {
    var offsets = {
      above: [{ x: -w / 2, y: -76 }, { x: -w - 18, y: -50 }, { x: 18, y: -50 }],
      below: [{ x: -w / 2, y: 26 }, { x: 18, y: 24 }, { x: -w - 18, y: 24 }],
      right: [{ x: 20, y: -h / 2 }, { x: 20, y: -70 }, { x: 20, y: 26 }],
      left: [{ x: -w - 20, y: -h / 2 }, { x: -w - 20, y: -70 }, { x: -w - 20, y: 26 }],
    };
    var candidates = (offsets[preferred] || []).concat(offsets.above, offsets.below, offsets.right, offsets.left);
    for (var i = 0; i < candidates.length; i++) {
      var c = candidates[i];
      var rect = {
        x: Math.max(bounds.x + 12, Math.min(bounds.x + bounds.w - w - 12, px + c.x)),
        y: Math.max(bounds.y + 12, Math.min(bounds.y + bounds.h - h - 12, py + c.y)),
        w: w,
        h: h,
      };
      var blocked = false;
      for (var j = 0; j < occupied.length; j++) {
        if (rectsOverlap(rect, occupied[j], 8)) {
          blocked = true;
          break;
        }
      }
      if (!blocked) {
        occupied.push(rect);
        return rect;
      }
    }
    var fallback = {
      x: Math.max(bounds.x + 12, Math.min(bounds.x + bounds.w - w - 12, px - w / 2)),
      y: Math.max(bounds.y + 12, Math.min(bounds.y + bounds.h - h - 12, py + 28)),
      w: w,
      h: h,
    };
    occupied.push(fallback);
    return fallback;
  }

  function drawFloatingLabel(label, value, point, bounds, preferred, accent, occupied) {
    var w = 178;
    var h = 56;
    var rect = placeLabel(point.x, point.y, w, h, bounds, preferred, occupied);
    ctx.save();
    ctx.strokeStyle = accent;
    ctx.globalAlpha = 0.68;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(point.x, point.y);
    ctx.lineTo(rect.x + rect.w / 2, rect.y + rect.h / 2);
    ctx.stroke();
    ctx.restore();

    drawGlassCard(rect.x, rect.y, rect.w, rect.h, 8, {
      fill: 'rgba(6, 14, 30, 0.76)',
      border: accent === palette.gold ? 'rgba(247, 200, 75, 0.44)' : 'rgba(255, 65, 109, 0.42)',
      blur: 16,
      offsetY: 8,
    });
    ctx.fillStyle = accent;
    ctx.font = font('900', 12);
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText(label, rect.x + 14, rect.y + 10);
    drawFittedText(formatAmount(value), rect.x + 14, rect.y + 28, rect.w - 28, '900', 20, 15, 'left', palette.text);
  }

  function drawHighestPoint(point) {
    ctx.save();
    ctx.shadowColor = 'rgba(247, 200, 75, 0.9)';
    ctx.shadowBlur = 24;
    ctx.fillStyle = palette.gold;
    ctx.beginPath();
    ctx.arc(point.x, point.y, 8, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.9)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(point.x, point.y, 4, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }

  function drawLowestPoint(point) {
    ctx.save();
    ctx.translate(point.x, point.y);
    ctx.rotate(Math.PI / 4);
    ctx.shadowColor = 'rgba(255, 52, 79, 0.86)';
    ctx.shadowBlur = 20;
    ctx.fillStyle = palette.danger;
    roundRect(-8, -8, 16, 16, 3);
    ctx.fill();
    ctx.shadowBlur = 0;
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.84)';
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.restore();
  }

  function drawLineChart(x, y, w, h, history) {
    if (history.length < 2) {
      ctx.fillStyle = 'rgba(226, 236, 255, 0.58)';
      ctx.font = font('700', 20);
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('Waiting for more data points', x + w / 2, y + h / 2 + 10);
      return null;
    }

    var values = history.map(function (item) { return Number(item.amount) || 0; });
    var minVal = Math.min.apply(null, values);
    var maxVal = Math.max.apply(null, values);
    var positiveLog = chartSettings.mode === 'log' && values.every(function (value) { return value > 0; });
    var scaledValues = values.map(function (value) { return chartScaleValue(value, positiveLog); });
    var scaledMinVal = Math.min.apply(null, scaledValues);
    var scaledMaxVal = Math.max.apply(null, scaledValues);
    var range = chartSettings.mode === 'log' ? Math.max(1e-6, scaledMaxVal - scaledMinVal) : Math.max(1, maxVal - minVal);
    var pad = chartSettings.mode === 'log'
      ? Math.max(range * 0.14, 0.08)
      : Math.max(range * 0.14, Math.abs(maxVal || minVal || 1) * 0.03, 1);
    var yMin = scaledMinVal - pad;
    var yMax = scaledMaxVal + pad;
    var yRange = Math.max(chartSettings.mode === 'log' ? 1e-6 : 1, yMax - yMin);
    var plot = {
      x: x + 92,
      y: y + 74,
      w: w - 132,
      h: h - 124,
      yMin: yMin,
      yMax: yMax,
      yRange: yRange,
      positiveLog: positiveLog,
    };

    ctx.save();
    ctx.strokeStyle = palette.grid;
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 7]);
    for (var row = 0; row <= 4; row++) {
      var yy = plot.y + (plot.h / 4) * row;
      ctx.beginPath();
      ctx.moveTo(plot.x, yy);
      ctx.lineTo(plot.x + plot.w, yy);
      ctx.stroke();
    }
    for (var col = 0; col <= 4; col++) {
      var xx = plot.x + (plot.w / 4) * col;
      ctx.beginPath();
      ctx.moveTo(xx, plot.y);
      ctx.lineTo(xx, plot.y + plot.h);
      ctx.stroke();
    }
    ctx.setLineDash([]);
    ctx.restore();

    if (!positiveLog && yMin < 0 && yMax > 0) {
      var zeroY = plot.y + plot.h - ((0 - yMin) / yRange) * plot.h;
      ctx.strokeStyle = 'rgba(247, 200, 75, 0.32)';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(plot.x, zeroY);
      ctx.lineTo(plot.x + plot.w, zeroY);
      ctx.stroke();
    }

    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = 'rgba(226, 236, 255, 0.62)';
    ctx.font = font('600', 12);
    for (var labelRow = 0; labelRow <= 4; labelRow++) {
      var labelValue = yMax - (yRange / 4) * labelRow;
      var labelY = plot.y + (plot.h / 4) * labelRow;
      ctx.fillText(formatAmount(chartUnscaleValue(labelValue, plot.positiveLog)), plot.x - 12, labelY);
    }

    if (chartSettings.mode === 'log') {
      ctx.textAlign = 'right';
      ctx.textBaseline = 'top';
      ctx.fillStyle = 'rgba(247, 200, 75, 0.72)';
      ctx.font = font('800', 12);
      ctx.fillText(positiveLog ? 'LOG10' : 'SIGNED LOG10', plot.x + plot.w, y + 28);
    }

    var areaGrad = ctx.createLinearGradient(0, plot.y, 0, plot.y + plot.h);
    areaGrad.addColorStop(0, 'rgba(255, 65, 109, 0.42)');
    areaGrad.addColorStop(0.62, 'rgba(255, 65, 109, 0.12)');
    areaGrad.addColorStop(1, 'rgba(255, 65, 109, 0.01)');
    ctx.fillStyle = areaGrad;
    ctx.beginPath();
    var first = pointAt(history, scaledValues, 0, plot);
    ctx.moveTo(first.x, plot.y + plot.h);
    for (var i = 0; i < history.length; i++) {
      var areaPoint = pointAt(history, scaledValues, i, plot);
      ctx.lineTo(areaPoint.x, areaPoint.y);
    }
    var last = pointAt(history, scaledValues, history.length - 1, plot);
    ctx.lineTo(last.x, plot.y + plot.h);
    ctx.closePath();
    ctx.fill();

    var lineGrad = ctx.createLinearGradient(plot.x, 0, plot.x + plot.w, 0);
    lineGrad.addColorStop(0, '#ff6b93');
    lineGrad.addColorStop(0.52, palette.red);
    lineGrad.addColorStop(1, '#ff2b56');
    ctx.save();
    ctx.strokeStyle = lineGrad;
    ctx.lineWidth = 3.5;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.shadowColor = 'rgba(255, 65, 109, 0.62)';
    ctx.shadowBlur = 16;
    ctx.beginPath();
    for (var lineIndex = 0; lineIndex < history.length; lineIndex++) {
      var linePoint = pointAt(history, scaledValues, lineIndex, plot);
      if (lineIndex === 0) ctx.moveTo(linePoint.x, linePoint.y);
      else ctx.lineTo(linePoint.x, linePoint.y);
    }
    ctx.stroke();
    ctx.restore();

    for (var dotIndex = 0; dotIndex < history.length; dotIndex++) {
      var dot = pointAt(history, scaledValues, dotIndex, plot);
      ctx.fillStyle = 'rgba(255, 255, 255, 0.78)';
      ctx.beginPath();
      ctx.arc(dot.x, dot.y, 3.2, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = palette.red;
      ctx.beginPath();
      ctx.arc(dot.x, dot.y, 1.8, 0, Math.PI * 2);
      ctx.fill();
    }

    var highIndex = values.indexOf(maxVal);
    var lowIndex = values.indexOf(minVal);
    var currentIndex = history.length - 1;
    var highPoint = pointAt(history, scaledValues, highIndex, plot);
    var lowPoint = pointAt(history, scaledValues, lowIndex, plot);
    var currentPoint = pointAt(history, scaledValues, currentIndex, plot);
    var occupied = [];
    var labelBounds = { x: x, y: y + 6, w: w, h: h - 12 };

    drawFloatingLabel('Highest', maxVal, highPoint, labelBounds, 'above', palette.gold, occupied);
    drawFloatingLabel('Lowest', minVal, lowPoint, labelBounds, 'below', palette.danger, occupied);
    if (currentIndex !== highIndex && currentIndex !== lowIndex) {
      drawFloatingLabel('Current', values[currentIndex], currentPoint, labelBounds, 'right', palette.red, occupied);
    }
    drawHighestPoint(highPoint);
    drawLowestPoint(lowPoint);

    ctx.save();
    ctx.shadowColor = 'rgba(255, 65, 109, 0.72)';
    ctx.shadowBlur = 20;
    ctx.fillStyle = palette.red;
    ctx.beginPath();
    ctx.arc(currentPoint.x, currentPoint.y, 7, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;
    ctx.fillStyle = '#ffffff';
    ctx.beginPath();
    ctx.arc(currentPoint.x, currentPoint.y, 3.2, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillStyle = 'rgba(226, 236, 255, 0.62)';
    ctx.font = font('600', 12);
    ctx.fillText(formatDate(history[0].date), plot.x, plot.y + plot.h + 18);
    ctx.fillText(formatDate(history[history.length - 1].date), plot.x + plot.w, plot.y + plot.h + 18);

    return { highest: maxVal, lowest: minVal };
  }

  function normalizedHistory() {
    var history = Array.isArray(posterData.history) ? posterData.history.slice() : [];
    history = history
      .filter(function (item) { return item && item.date && item.amount !== undefined; })
      .map(function (item) { return { date: item.date, amount: Number(item.amount) || 0 }; })
      .sort(function (a, b) { return String(a.date).localeCompare(String(b.date)); });
    if (!history.length) {
      history.push({ date: new Date().toISOString(), amount: Number(posterData.currentAmount) || 0 });
    }
    return history;
  }

  function drawPoster() {
    var history = normalizedHistory();
    var currentAmount = Number(posterData.currentAmount) || 0;
    var activity = posterData.activity || {};
    var titleName = playerTitle(posterData.rank, posterData.totalPlayers);

    ctx.clearRect(0, 0, W, H);
    drawBackground();
    drawHeader(currentAmount, posterData.coinName || 'Fermat Coin', posterData.nickname || posterData.username || '', titleName);

    var leftX = 48;
    var leftW = 330;
    var rightX = 426;
    var rightW = 726;
    var topY = 172;
    var chartH = 354;
    var gap = 14;

    drawRadarChart(leftX, topY, leftW, 258, posterData.radarStats || {});
    drawRankBadge(leftX, 444, leftW, 192, posterData.rank, posterData.totalPlayers);
    drawLineChart(rightX, topY, rightW, chartH, history);

    var cardY = topY + chartH + 22;
    var cardH = 88;
    var cardW = (rightW - gap * 2) / 3;
    drawMetricCard(rightX, cardY, cardW, cardH, '猜测次数', formatAmount(activity.betCount), palette.gold);
    drawMetricCard(rightX + cardW + gap, cardY, cardW, cardH, '贷款次数', formatAmount(activity.loanCount), palette.gold);
    drawMetricCard(rightX + (cardW + gap) * 2, cardY, cardW, cardH, '注册天数', formatAmount(activity.registrationDays), palette.gold);

    var bottomAccent = ctx.createLinearGradient(40, 0, W - 40, 0);
    bottomAccent.addColorStop(0, 'rgba(247, 200, 75, 0)');
    bottomAccent.addColorStop(0.24, 'rgba(247, 200, 75, 0.58)');
    bottomAccent.addColorStop(0.7, 'rgba(255, 65, 109, 0.42)');
    bottomAccent.addColorStop(1, 'rgba(255, 65, 109, 0)');
    ctx.fillStyle = bottomAccent;
    ctx.fillRect(40, H - 4, W - 80, 3);
  }

  window.downloadPoster = function downloadPoster() {
    var btn = document.getElementById('dl-btn');
    if (btn) {
      btn.textContent = '生成中...';
      btn.disabled = true;
    }
    canvas.toBlob(function (blob) {
      var url = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = url;
      a.download = 'fermat_poster_' + (posterData.nickname || posterData.username || 'player') + '.png';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      if (btn) {
        btn.textContent = '下载图片';
        btn.disabled = false;
      }
    }, 'image/png');
  };

  function initBackgroundControls() {
    var fileInput = document.getElementById('poster-bg-file');
    var xInput = document.getElementById('poster-bg-x');
    var yInput = document.getElementById('poster-bg-y');
    var zoomInput = document.getElementById('poster-bg-zoom');
    var opacityInput = document.getElementById('poster-bg-opacity');
    var resetButton = document.getElementById('poster-bg-reset');
    if (!fileInput || !xInput || !yInput || !zoomInput || !opacityInput) return;

    function syncSettings() {
      bgSettings.x = clamp(Number(xInput.value) / 100, -1, 1);
      bgSettings.y = clamp(Number(yInput.value) / 100, -1, 1);
      bgSettings.zoom = clamp(Number(zoomInput.value) / 100, 1, 2.2);
      bgSettings.opacity = clamp(Number(opacityInput.value) / 100, 0, 1);
      drawPoster();
    }

    fileInput.addEventListener('change', function () {
      var file = fileInput.files && fileInput.files[0];
      if (!file) return;
      if (customBgUrl) URL.revokeObjectURL(customBgUrl);
      customBgUrl = URL.createObjectURL(file);
      customBg = new Image();
      customBg.onload = function () {
        updateMaskColorFromImage(customBg);
        drawPoster();
      };
      customBg.onerror = function () {
        customBg = null;
        drawPoster();
      };
      customBg.src = customBgUrl;
    });

    [xInput, yInput, zoomInput, opacityInput].forEach(function (input) {
      input.addEventListener('input', syncSettings);
    });

    if (resetButton) {
      resetButton.addEventListener('click', function () {
        if (customBgUrl) URL.revokeObjectURL(customBgUrl);
        customBgUrl = '';
        customBg = null;
        fileInput.value = '';
        xInput.value = '0';
        yInput.value = '0';
        zoomInput.value = '100';
        opacityInput.value = '100';
        syncSettings();
      });
    }
  }

  function updateMaskColorFromImage(image) {
    var colorInput = document.getElementById('poster-mask-color');
    if (!colorInput) return;
    extractDominantColor(image, function (hex) {
      colorInput.value = hex;
      maskSettings.color = hex;
      drawPoster();
    });
  }

  function initMaskControls() {
    var modeInput = document.getElementById('poster-mask-mode');
    var colorInput = document.getElementById('poster-mask-color');
    var colorFileInput = document.getElementById('poster-mask-color-file');
    var angleRangeInput = document.getElementById('poster-mask-angle');
    var angleNumberInput = document.getElementById('poster-mask-angle-number');
    var maxInput = document.getElementById('poster-mask-max');
    var minInput = document.getElementById('poster-mask-min');
    var curveInput = document.getElementById('poster-mask-curve');
    var resetButton = document.getElementById('poster-mask-reset');
    var autoColorButton = document.getElementById('poster-mask-auto-color');
    if (!modeInput || !colorInput || !angleRangeInput || !angleNumberInput || !maxInput || !minInput || !curveInput) return;

    function setCustomMode() {
      modeInput.value = 'custom';
      maskSettings.mode = 'custom';
    }

    function syncMaskSettings(changedInput) {
      if (changedInput === angleRangeInput) angleNumberInput.value = angleRangeInput.value;
      if (changedInput === angleNumberInput) {
        var angleValue = clamp(Number(angleNumberInput.value) || 0, 0, 360);
        angleRangeInput.value = angleValue;
        angleNumberInput.value = angleValue;
      }

      maskSettings.mode = modeInput.value === 'custom' ? 'custom' : 'default';
      maskSettings.color = colorInput.value || maskSettings.color;
      maskSettings.angle = clamp(Number(angleRangeInput.value) || 0, 0, 360);
      maskSettings.maxOpacity = clamp(Number(maxInput.value) / 100, 0, 1);
      maskSettings.minOpacity = clamp(Number(minInput.value) / 100, 0, 1);
      maskSettings.curve = curveInput.value || 'linear';
      drawPoster();
    }

    modeInput.addEventListener('change', function () {
      syncMaskSettings(modeInput);
    });

    [colorInput, angleRangeInput, angleNumberInput, maxInput, minInput, curveInput].forEach(function (input) {
      input.addEventListener('input', function () {
        if (input !== modeInput) setCustomMode();
        syncMaskSettings(input);
      });
      input.addEventListener('change', function () {
        if (input !== modeInput) setCustomMode();
        syncMaskSettings(input);
      });
    });

    if (colorFileInput) {
      colorFileInput.addEventListener('change', function () {
        var file = colorFileInput.files && colorFileInput.files[0];
        if (!file) return;
        var url = URL.createObjectURL(file);
        var image = new Image();
        image.onload = function () {
          var cleanup = function () { URL.revokeObjectURL(url); };
          setCustomMode();
          extractDominantColor(image, function (hex) {
            cleanup();
            colorInput.value = hex;
            maskSettings.color = hex;
            syncMaskSettings(colorInput);
          });
          window.setTimeout(cleanup, 0);
        };
        image.onerror = function () {
          URL.revokeObjectURL(url);
        };
        image.src = url;
      });
    }

    if (autoColorButton) {
      autoColorButton.addEventListener('click', function () {
        if (!customBg || !customBg.naturalWidth) return;
        setCustomMode();
        updateMaskColorFromImage(customBg);
        syncMaskSettings(colorInput);
      });
    }

    if (resetButton) {
      resetButton.addEventListener('click', function () {
        modeInput.value = 'default';
        colorInput.value = '#071426';
        angleRangeInput.value = '325';
        angleNumberInput.value = '325';
        maxInput.value = '100';
        minInput.value = '50';
        curveInput.value = 'power';
        syncMaskSettings(modeInput);
      });
    }

    syncMaskSettings(modeInput);
  }

  function initChartModeControls() {
    var modeInput = document.getElementById('poster-chart-mode');
    if (!modeInput) return;
    modeInput.value = chartSettings.mode;
    modeInput.addEventListener('change', function () {
      chartSettings.mode = modeInput.value === 'log' ? 'log' : 'default';
      posterData.chartMode = chartSettings.mode;
      drawPoster();
    });
  }

  initBackgroundControls();
  initMaskControls();
  initChartModeControls();

  window.__fermatPoster = {
    drawPoster: drawPoster,
    formatAmount: formatAmount,
    extractDominantColor: extractDominantColor,
  };
})();
