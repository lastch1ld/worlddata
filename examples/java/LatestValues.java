import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/**
 * Prints the most recent value of every series in a worlddata CSV.
 * Plain JDK 17+, no build tool:
 *
 *   java examples/java/LatestValues.java                        (central_bank_rates)
 *   java examples/java/LatestValues.java data/gold_monthly.csv
 */
public class LatestValues {

    public static void main(String[] args) throws IOException {
        Path csv = Path.of(args.length > 0 ? args[0] : "data/central_bank_rates.csv");
        List<String> lines = Files.readAllLines(csv);

        // Every dataset is tidy long format, but extra columns vary, so look columns up by name.
        List<String> header = split(lines.get(0));
        int date = header.indexOf("date"), series = header.indexOf("series"), value = header.indexOf("value");
        if (date < 0 || series < 0 || value < 0) {
            throw new IllegalArgumentException(csv + " has no date/series/value columns: " + header);
        }

        // ISO dates compare correctly as strings.
        Map<String, String[]> latest = new TreeMap<>();
        for (String line : lines.subList(1, lines.size())) {
            List<String> row = split(line);
            String[] seen = latest.get(row.get(series));
            if (seen == null || row.get(date).compareTo(seen[0]) > 0) {
                latest.put(row.get(series), new String[] {row.get(date), row.get(value)});
            }
        }

        latest.forEach((name, dv) -> System.out.printf("%-40s %s  %s%n", name, dv[0], dv[1]));
        System.out.printf("%n%d series, %d rows%n", latest.size(), lines.size() - 1);
    }

    /** RFC 4180 split: handles quoted fields with commas and doubled quotes. */
    static List<String> split(String line) {
        List<String> out = new ArrayList<>();
        StringBuilder cell = new StringBuilder();
        boolean quoted = false;
        for (int i = 0; i < line.length(); i++) {
            char c = line.charAt(i);
            if (quoted && c == '"' && i + 1 < line.length() && line.charAt(i + 1) == '"') { cell.append('"'); i++; }
            else if (c == '"') quoted = !quoted;
            else if (c == ',' && !quoted) { out.add(cell.toString()); cell.setLength(0); }
            else cell.append(c);
        }
        out.add(cell.toString());
        return out;
    }
}
