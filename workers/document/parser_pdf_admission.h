// Application-owned admission for the pinned docling-parse/QPDF derivative.
// Reads original dictionaries and bounded encoded streams before pixel decoding.
#ifndef RO_PARSER_PDF_ADMISSION_H
#define RO_PARSER_PDF_ADMISSION_H

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#include <nlohmann/json.hpp>
#include <qpdf/QPDFPageObjectHelper.hh>
#include <qpdf/Pipeline.hh>

namespace pdflib::ro_parser
{
  constexpr std::uint64_t max_page_pixels = 40000000;
  constexpr std::size_t max_stream_bytes = 128 * 1024 * 1024;

  struct bounded_bytes: Pipeline
  {
    std::string data;
    bounded_bytes(): Pipeline("ro-bounded-stream", nullptr) {}
    void write(unsigned char const* value, std::size_t size) override
    {
      if(size > max_stream_bytes - data.size())
        throw std::runtime_error("parser-resource-limit");
      data.append(reinterpret_cast<char const*>(value), size);
    }
    void finish() override {}
  };

  inline std::uint32_t be32(std::string const& data, std::size_t offset)
  {
    if(offset > data.size() || data.size() - offset < 4)
      throw std::runtime_error("parser-image-header-invalid");
    auto p = reinterpret_cast<unsigned char const*>(data.data() + offset);
    return (std::uint32_t(p[0]) << 24) | (std::uint32_t(p[1]) << 16) |
           (std::uint32_t(p[2]) << 8) | p[3];
  }

  inline std::uint16_t be16(std::string const& data, std::size_t offset)
  {
    if(offset > data.size() || data.size() - offset < 2)
      throw std::runtime_error("parser-image-header-invalid");
    auto p = reinterpret_cast<unsigned char const*>(data.data() + offset);
    return (std::uint16_t(p[0]) << 8) | p[1];
  }

  inline std::uint64_t pixels(std::uint64_t width, std::uint64_t height)
  {
    if(width == 0 || height == 0 || width > max_page_pixels / height)
      throw std::runtime_error("parser-page-pixel-limit");
    return width * height;
  }

  inline std::uint64_t dimension(QPDFObjectHandle value)
  {
    if(!value.isInteger() || value.getIntValue() <= 0 ||
       value.getIntValue() > static_cast<long long>(max_page_pixels))
      throw std::runtime_error("parser-page-pixel-limit");
    return static_cast<std::uint64_t>(value.getIntValue());
  }

  inline void codec_dimensions(std::string const& data, std::string const& filter,
                               std::uint64_t width, std::uint64_t height)
  {
    auto agree = [&](std::uint64_t w, std::uint64_t h) {
      pixels(w, h);
      if(w != width || h != height) throw std::runtime_error("parser-image-header-mismatch");
    };
    if(filter == "/DCTDecode" || filter == "/DCT")
      {
        if(be16(data, 0) != 0xffd8) throw std::runtime_error("parser-image-header-invalid");
        std::size_t offset = 2;
        for(int count = 0; count < 65536 && offset < data.size(); ++count)
          {
            if(static_cast<unsigned char>(data[offset++]) != 0xff)
              throw std::runtime_error("parser-image-header-invalid");
            while(offset < data.size() && static_cast<unsigned char>(data[offset]) == 0xff) ++offset;
            if(offset >= data.size()) break;
            auto marker = static_cast<unsigned char>(data[offset++]);
            if(marker == 0xd9 || marker == 0xda || marker == 0x00) break;
            if(marker == 0x01 || (marker >= 0xd0 && marker <= 0xd8)) continue;
            auto length = be16(data, offset);
            if(length < 2 || length > data.size() - offset)
              throw std::runtime_error("parser-image-header-invalid");
            bool sof = marker >= 0xc0 && marker <= 0xcf && marker != 0xc4 && marker != 0xc8 && marker != 0xcc;
            if(sof)
              {
                if(length < 8) throw std::runtime_error("parser-image-header-invalid");
                agree(be16(data, offset + 5), be16(data, offset + 3));
                return;
              }
            offset += length;
          }
      }
    else if(filter == "/JPXDecode")
      {
        std::size_t offset = 0, size = data.size();
        if(size >= 12 && be32(data, 4) == 0x6a502020)
          {
            bool found = false;
            while(offset < size)
              {
                std::uint64_t length = be32(data, offset);
                auto type = be32(data, offset + 4);
                std::size_t header = 8;
                if(length == 1)
                  { length = (std::uint64_t(be32(data, offset + 8)) << 32) | be32(data, offset + 12); header = 16; }
                if(length == 0) length = size - offset;
                if(length < header || length > size - offset) throw std::runtime_error("parser-image-header-invalid");
                if(type == 0x6a703263) { offset += header; size = offset + length - header; found = true; break; }
                offset += static_cast<std::size_t>(length);
              }
            if(!found) throw std::runtime_error("parser-image-header-invalid");
          }
        if(be16(data, offset) != 0xff4f || be16(data, offset + 2) != 0xff51 ||
           be16(data, offset + 4) < 38 || offset + be16(data, offset + 4) + 4 > size)
          throw std::runtime_error("parser-image-header-invalid");
        auto xs = be32(data, offset + 8), ys = be32(data, offset + 12);
        auto xo = be32(data, offset + 16), yo = be32(data, offset + 20);
        if(xs <= xo || ys <= yo) throw std::runtime_error("parser-image-header-invalid");
        agree(xs - xo, ys - yo);
        auto xt = be32(data, offset + 24), yt = be32(data, offset + 28);
        auto xto = be32(data, offset + 32), yto = be32(data, offset + 36);
        auto components = be16(data, offset + 40);
        if(components == 0 || components > 4 || be16(data, offset + 4) != 38 + 3 * components ||
           xt == 0 || yt == 0 || xto > xo || yto > yo ||
           std::uint64_t(xto) + xt <= xo || std::uint64_t(yto) + yt <= yo)
          throw std::runtime_error("parser-image-header-invalid");
        auto nx = (std::uint64_t(xs) - xto + xt - 1) / xt;
        auto ny = (std::uint64_t(ys) - yto + yt - 1) / yt;
        if(nx == 0 || ny == 0 || nx > 65536 / ny || nx * ny > 65536 / components)
          throw std::runtime_error("parser-resource-limit");
        for(unsigned i = 0; i < components; ++i)
          {
            auto precision = static_cast<unsigned char>(data[offset + 42 + 3 * i]);
            auto xr = static_cast<unsigned char>(data[offset + 43 + 3 * i]);
            auto yr = static_cast<unsigned char>(data[offset + 44 + 3 * i]);
            if((precision & 0x7f) >= 16 || xr == 0 || yr == 0)
              throw std::runtime_error("parser-image-header-invalid");
          }
        return;
      }
    else return;
    throw std::runtime_error("parser-image-header-invalid");
  }

  inline void image_stream(QPDFObjectHandle stream, std::uint64_t width, std::uint64_t height)
  {
    // Predictor constructors allocate rows before emitting any decoded bytes.
    auto params = stream.getDict().getKey("/DecodeParms");
    if(params.isArray())
      {
        if(params.getArrayNItems() != 1) throw std::runtime_error("parser-image-header-invalid");
        params = params.getArrayItem(0);
      }
    if(!params.isNull() && !params.isDictionary()) throw std::runtime_error("parser-image-header-invalid");
    if(params.isDictionary())
      {
        for(auto key : {"/Columns", "/Rows"})
          {
            auto value = params.getKey(key);
            if(value.isNull()) continue;
            if(!value.isInteger() || value.getIntValue() < 0) throw std::runtime_error("parser-image-header-invalid");
            if(value.getIntValue() != 0 && static_cast<std::uint64_t>(value.getIntValue()) != (std::string(key) == "/Columns" ? width : height))
              throw std::runtime_error("parser-image-header-mismatch");
          }
        std::uint64_t colors = 1, bits = 8, columns = 1;
        for(auto [key, target] : {std::pair{"/Colors", &colors}, {"/BitsPerComponent", &bits}, {"/Columns", &columns}})
          {
            auto value = params.getKey(key);
            if(value.isNull()) continue;
            if(!value.isInteger() || value.getIntValue() <= 0) throw std::runtime_error("parser-image-header-invalid");
            *target = static_cast<std::uint64_t>(value.getIntValue());
          }
        if(colors > 4 || (bits != 1 && bits != 2 && bits != 4 && bits != 8 && bits != 16) ||
           columns > max_stream_bytes / (colors * bits))
          throw std::runtime_error("parser-resource-limit");
      }
    auto filter = stream.getDict().getKey("/Filter");
    if(filter.isArray())
      {
        if(filter.getArrayNItems() != 1) throw std::runtime_error("parser-image-filter-unverified");
        filter = filter.getArrayItem(0);
      }
    auto name = filter.isName() ? filter.getName() : std::string();
    if(!filter.isNull() && !filter.isName()) throw std::runtime_error("parser-image-filter-unverified");
    // The independently packaged PDFium renderer has separate JBIG2 symbol,
    // pattern and retained-region allocations. Their compressed dimensions
    // are not proven by the page header. Deny before either native consumer.
    if(name == "/JBIG2Decode") throw std::runtime_error("parser-image-codec-unverified");
    bool codec = name == "/DCTDecode" || name == "/DCT" || name == "/JPXDecode";
    bounded_bytes bytes;
    bool filtering = false;
    if(!stream.pipeStreamData(&bytes, &filtering, 0, codec ? qpdf_dl_none : qpdf_dl_generalized, true, false))
      throw std::runtime_error("parser-image-filter-unverified");
    if(codec) codec_dimensions(bytes.data, name, width, height);
    else if(!name.empty() && !filtering && name != "/CCITTFaxDecode" && name != "/CCF")
      throw std::runtime_error("parser-image-filter-unverified");
  }

  inline std::array<double, 4> box(QPDFObjectHandle value)
  {
    if(!value.isArray() || value.getArrayNItems() != 4)
      throw std::runtime_error("parser-page-box-invalid");
    std::array<double, 4> result;
    for(int i = 0; i < 4; ++i)
      {
        auto number = value.getArrayItem(i);
        if(!number.isNumber() || !std::isfinite(number.getNumericValue()))
          throw std::runtime_error("parser-page-box-invalid");
        result[i] = number.getNumericValue();
      }
    if(result[2] <= result[0] || result[3] <= result[1])
      throw std::runtime_error("parser-page-box-invalid");
    return result;
  }

  struct image_admission
  {
    std::set<QPDFObjGen> visited;
    std::set<QPDFObjGen> content_visited;
    std::uint64_t image_pixels = 0;
    std::size_t nodes = 0;

    void add(std::uint64_t count)
    {
      if(count > max_page_pixels - image_pixels)
        throw std::runtime_error("parser-page-pixel-limit");
      image_pixels += count;
    }

    void mask_chain(QPDFObjectHandle stream)
    {
      std::set<QPDFObjGen> chain;
      for(int depth = 0; stream.isStream(); ++depth)
        {
          if(depth >= 64 || (stream.isIndirect() && !chain.insert(stream.getObjGen()).second))
            throw std::runtime_error("parser-resource-cycle");
          auto dict = stream.getDict();
          auto mask = dict.getKey("/SMask");
          if(!mask.isStream()) mask = dict.getKey("/Mask");
          stream = mask;
        }
    }

    struct inline_admission: QPDFObjectHandle::ParserCallbacks
    {
      image_admission& owner;
      QPDF* document;
      bool active = false, ready = false;
      std::vector<QPDFObjectHandle> parameters;
      QPDFObjectHandle dictionary;
      inline_admission(image_admission& owner_, QPDF* doc): owner(owner_), document(doc) {}
      void handleObject(QPDFObjectHandle obj) override
      {
        if(obj.isOperator())
          {
            auto op = obj.getOperatorValue();
            if(op == "BI")
              {
                if(active) throw std::runtime_error("parser-inline-image-invalid");
                active = true; ready = false; parameters.clear();
              }
            else if(active && op == "ID")
              {
                if(ready || parameters.size() % 2 != 0)
                  throw std::runtime_error("parser-inline-image-invalid");
                dictionary = QPDFObjectHandle::newDictionary();
                for(std::size_t i = 0; i < parameters.size(); i += 2)
                  {
                    if(!parameters[i].isName()) throw std::runtime_error("parser-inline-image-invalid");
                    auto key = parameters[i].getName();
                    if(key == "/W") key = "/Width";
                    else if(key == "/H") key = "/Height";
                    else if(key == "/F") key = "/Filter";
                    else if(key == "/DP") key = "/DecodeParms";
                    if(dictionary.hasKey(key)) throw std::runtime_error("parser-inline-image-invalid");
                    dictionary.replaceKey(key, parameters[i + 1]);
                  }
                owner.add(pixels(dimension(dictionary.getKey("/Width")), dimension(dictionary.getKey("/Height"))));
                ready = true;
              }
            else if(active && op == "EI")
              {
                if(!ready) throw std::runtime_error("parser-inline-image-invalid");
                active = ready = false;
              }
            else if(active) throw std::runtime_error("parser-inline-image-invalid");
          }
        else if(obj.isInlineImage())
          {
            if(!active || !ready) throw std::runtime_error("parser-inline-image-invalid");
            auto data = obj.getInlineImageValue();
            if(data.size() > max_stream_bytes) throw std::runtime_error("parser-resource-limit");
            auto stream = QPDFObjectHandle::newStream(document, data);
            for(auto [key, value] : dictionary.getDictAsMap()) stream.getDict().replaceKey(key, value);
            image_stream(stream, dimension(dictionary.getKey("/Width")), dimension(dictionary.getKey("/Height")));
          }
        else if(active)
          {
            if(ready || parameters.size() >= 128) throw std::runtime_error("parser-inline-image-invalid");
            parameters.push_back(obj);
          }
      }
      void handleEOF() override
      {
        if(active) throw std::runtime_error("parser-inline-image-invalid");
      }
    };

    void content(QPDFObjectHandle obj, QPDF* document)
    {
      if(obj.isNull()) return;
      if(obj.isIndirect() && !content_visited.insert(obj.getObjGen()).second) return;
      inline_admission callback(*this, document);
      // The application derivative also caps QPDF's concatenated content
      // buffer before allocation; this pass does not decode image pixels.
      QPDFObjectHandle::parseContentStream(obj, &callback);
    }

    void walk(QPDFObjectHandle obj, std::size_t depth = 0, std::string role = "")
    {
      if(++nodes > 100000 || depth > 64)
        throw std::runtime_error("parser-resource-limit");
      if(obj.isStream() && (role == "glyph" || role == "appearance")) content(obj, obj.getOwningQPDF());
      if(obj.isIndirect() && !visited.insert(obj.getObjGen()).second) return;
      if(obj.isArray())
        {
          auto count = obj.getArrayNItems();
          if(count > 100000) throw std::runtime_error("parser-resource-limit");
          for(int i = 0; i < count; ++i) walk(obj.getArrayItem(i), depth + 1, role);
          return;
        }
      bool stream = obj.isStream();
      auto dict = stream ? obj.getDict() : obj;
      if(!dict.isDictionary()) return;
      if(stream)
        {
          auto filters = dict.getKey("/Filter");
          std::vector<QPDFObjectHandle> names;
          if(filters.isArray())
            for(int i = 0; i < filters.getArrayNItems(); ++i) names.push_back(filters.getArrayItem(i));
          else names.push_back(filters);
          for(auto filter : names)
            if(filter.isName() && filter.getName() == "/JBIG2Decode")
              throw std::runtime_error("parser-image-codec-unverified");
        }
      auto subtype = dict.getKey("/Subtype");
      if(stream && subtype.isName() && subtype.getName() == "/Image")
        {
          auto width = dimension(dict.getKey("/Width"));
          auto height = dimension(dict.getKey("/Height"));
          add(pixels(width, height));
          image_stream(obj, width, height);
          mask_chain(obj);
          // The native decoder resolves alpha onto the finer crossed grid.
          auto mask = dict.getKey("/SMask");
          if(!mask.isStream()) mask = dict.getKey("/Mask");
          if(mask.isStream())
            {
              auto md = mask.getDict();
              add(pixels(std::max(width, dimension(md.getKey("/Width"))),
                         std::max(height, dimension(md.getKey("/Height")))));
            }
        }
      else if(stream && ((subtype.isName() && subtype.getName() == "/Form") ||
                         dict.hasKey("/PatternType") || dict.hasKey("/BBox")))
        {
          content(obj, obj.getOwningQPDF());
        }
      auto entries = dict.getDictAsMap();
      if(entries.size() > 100000) throw std::runtime_error("parser-resource-limit");
      for(auto& [key, value] : entries)
        {
          // /P and /Parent are also legal resource and glyph names. Only
          // actual page-tree/annotation/font reverse links are excluded.
          auto type = dict.getKey("/Type");
          bool structural = (type.isName() && (type.getName() == "/Page" || type.getName() == "/Pages" ||
                             type.getName() == "/Annot" || type.getName() == "/Font")) || role == "annotation";
          if(structural && (key == "/Parent" || key == "/P")) continue;
          std::string child_role;
          if(key == "/CharProcs" || role == "glyph") child_role = "glyph";
          if(key == "/AP" || role == "appearance") child_role = "appearance";
          // Resources inside a glyph/appearance are resource dictionaries.
          if(key == "/Resources") child_role = "";
          walk(value, depth + 1, child_role);
        }
    }
  };

  inline nlohmann::json page_admission(QPDFObjectHandle page)
  {
    if(!page.isDictionary()) throw std::runtime_error("parser-page-dictionary-invalid");
    QPDFPageObjectHelper helper(page);
    auto media = box(helper.getMediaBox(false));
    auto crop = box(helper.getCropBox(false, false));
    if(crop[0] < media[0] || crop[1] < media[1] || crop[2] > media[2] || crop[3] > media[3])
      throw std::runtime_error("parser-page-boundary-unsupported");
    double unit = 1.0;
    // Absence is the only default; an explicit invalid scalar stays adverse.
    if(page.getDictAsMap().count("/UserUnit"))
      {
        auto value = page.getKey("/UserUnit");
        if(!value.isNumber() || !std::isfinite(value.getNumericValue()) ||
           value.getNumericValue() <= 0 || value.getNumericValue() > 75000)
          throw std::runtime_error("parser-page-scale-invalid");
        unit = value.getNumericValue();
      }
    int rotation = 0;
    auto angle = helper.getAttribute("/Rotate", false);
    if(!angle.isNull())
      {
        if(!angle.isInteger() || angle.getIntValue() % 90 != 0)
          throw std::runtime_error("parser-page-rotation-invalid");
        rotation = static_cast<int>((angle.getIntValue() % 360 + 360) % 360);
      }
    // Admission precedes resource decoding and any page raster. Physical
    // dimensions are checked too, although this backend renders in PDF units.
    for(double scale : {1.5, 1.5 * unit})
      {
        double w = std::ceil((crop[2] - crop[0]) * scale);
        double h = std::ceil((crop[3] - crop[1]) * scale);
        if(!std::isfinite(w) || !std::isfinite(h) || w <= 0 || h <= 0 ||
           w > max_page_pixels || h > max_page_pixels || w * h > max_page_pixels)
          throw std::runtime_error("parser-page-pixel-limit");
      }
    image_admission images;
    images.walk(helper.getAttribute("/Resources", false));
    images.walk(page.getKey("/Annots"), 0, "annotation");
    images.content(page.getKey("/Contents"), page.getOwningQPDF());
    return {{"mediaBox", media}, {"cropBox", crop}, {"rotation", rotation},
            {"userUnit", unit}, {"imagePixels", images.image_pixels}};
  }
}
#endif
