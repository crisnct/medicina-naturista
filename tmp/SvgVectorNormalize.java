import java.awt.Font;
import java.awt.font.FontRenderContext;
import java.awt.geom.PathIterator;
import java.nio.file.Path;
import java.util.Locale;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.TransformerFactory;
import javax.xml.transform.OutputKeys;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;
import org.w3c.dom.Element;

public class SvgVectorNormalize {
  static final String NS = "http://www.w3.org/2000/svg";
  static String number(double value) { return String.format(Locale.ROOT,"%.3f",value); }
  public static void main(String[] args) throws Exception {
    var factory = DocumentBuilderFactory.newInstance();
    factory.setNamespaceAware(true);
    var document = factory.newDocumentBuilder().parse(Path.of(args[0]).toFile());
    var context = new FontRenderContext(null, true, true);
    var nodes = document.getElementsByTagNameNS(NS,"text");
    while (nodes.getLength() > 0) {
      var text = (Element)nodes.item(0);
      var label = text.getTextContent();
      var family = text.getAttribute("font-family").split(",")[0].trim();
      var weight = text.getAttribute("font-weight");
      var font = new Font(family, weight.equals("700") || weight.equals("600") ? Font.BOLD : Font.PLAIN, 1)
        .deriveFont(Float.parseFloat(text.getAttribute("font-size")));
      var glyphs = font.createGlyphVector(context, label);
      float x = Float.parseFloat(text.getAttribute("x"));
      float y = Float.parseFloat(text.getAttribute("y"));
      var anchor = text.getAttribute("text-anchor");
      float advance = (float)glyphs.getLogicalBounds().getWidth();
      if (anchor.equals("middle")) x -= advance / 2;
      else if (anchor.equals("end")) x -= advance;
      var outline = glyphs.getOutline(x,y).getPathIterator(null);
      var coordinates = new double[6];
      var path = new StringBuilder();
      while (!outline.isDone()) {
        int segment = outline.currentSegment(coordinates);
        String command = switch (segment) {
          case PathIterator.SEG_MOVETO -> "M";
          case PathIterator.SEG_LINETO -> "L";
          case PathIterator.SEG_QUADTO -> "Q";
          case PathIterator.SEG_CUBICTO -> "C";
          default -> "Z";
        };
        path.append(command);
        int count = switch (segment) {
          case PathIterator.SEG_MOVETO, PathIterator.SEG_LINETO -> 2;
          case PathIterator.SEG_QUADTO -> 4;
          case PathIterator.SEG_CUBICTO -> 6;
          default -> 0;
        };
        for (int i=0; i<count; i++) path.append(number(coordinates[i])).append(' ');
        outline.next();
      }
      var geometry = document.createElementNS(NS,"path");
      geometry.setAttribute("d",path.toString());
      geometry.setAttribute("fill",text.getAttribute("fill"));
      var title = document.createElementNS(NS,"title");
      title.setTextContent(label);
      geometry.appendChild(title);
      text.getParentNode().replaceChild(geometry,text);
    }
    var transformer = TransformerFactory.newInstance().newTransformer();
    transformer.setOutputProperty(OutputKeys.ENCODING,"UTF-8");
    transformer.setOutputProperty(OutputKeys.INDENT,"yes");
    transformer.transform(new DOMSource(document), new StreamResult(Path.of(args[1]).toFile()));
    System.out.println("Converted all text to independent vector geometry");
  }
}
