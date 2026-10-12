import com.github.weisj.jsvg.SVGDocument;
import com.github.weisj.jsvg.parser.SVGLoader;
import java.awt.image.BufferedImage;
import java.nio.file.Path;
import javax.imageio.ImageIO;
public class SvgPreviewCheck {
  public static void main(String[] args) throws Exception {
    var input = Path.of(args[0]);
    var document = new SVGLoader().load(input.toUri().toURL());
    if (document == null) throw new IllegalStateException("SVG loading failed");
    int width = (int)document.size().width;
    int height = (int)document.size().height;
    var image = new BufferedImage(width, height, BufferedImage.TYPE_INT_ARGB);
    var graphics = image.createGraphics();
    document.render(null, graphics);
    graphics.dispose();
    long painted = 0;
    for (int y = 0; y < height; y++) for (int x = 0; x < width; x++) {
      int pixel = image.getRGB(x,y);
      if ((pixel >>> 24) != 0 && (pixel & 0xFFFFFF) != 0xFFFFFF) painted++;
    }
    if (painted < 10000) throw new IllegalStateException("Blank SVG: " + painted);
    ImageIO.write(image, "png", Path.of(args[1]).toFile());
    System.out.println("IntelliJ JSVG rendered: " + width + "x" + height + "; colored pixels=" + painted);
  }
}
