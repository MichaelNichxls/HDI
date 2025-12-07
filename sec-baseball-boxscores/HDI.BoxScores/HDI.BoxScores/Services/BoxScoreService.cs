using Google.Apis.Sheets.v4;
using Google.Apis.Sheets.v4.Data;
using HDI.BoxScores.Configuration;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using OpenQA.Selenium;
using OpenQA.Selenium.Support.Events;
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Security.Claims;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using static Google.Apis.Sheets.v4.SpreadsheetsResource.ValuesResource;
using GoogleUtilities = Google.Apis.Util.Utilities;

namespace HDI.BoxScores.Services;

public sealed class BoxScoreService(
    SheetsService sheets,
    IWebDriver driver,
    IOptions<BoxScoreOptions> options,
    ILogger<BoxScoreService> logger)
    : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken cancellationToken)
    {
        EventFiringWebDriver eventDriver = new(driver);

        eventDriver.Navigating += (sender, e) => logger.LogInformation("Navigating to {Url}", new Uri(e.Url!));
        eventDriver.NavigatingBack += (sender, e) => logger.LogInformation("Navigating back");
        eventDriver.FindingElement += (sender, e) => logger.LogDebug("Finding element by {FindMethod}", e.FindMethod.ToString());

        try
        {
            IList<Uri> scheduleUrls = [], boxScoreUrls = [];

            Uri secUrl = new("https://www.secsports.com");
            await eventDriver.Navigate().GoToUrlAsync(secUrl).ConfigureAwait(false);

            foreach (IWebElement schoolElement in eventDriver.FindElements(By.XPath("""//header//li[.//text()[normalize-space() = "Schools"]]//li/a""")))
                scheduleUrls.Add(new(secUrl, $"schedule/baseball/{schoolElement.GetDomAttribute("href")!.Split('/', '\\')[^1]}?view=season"));

            foreach (Uri scheduleUrl in scheduleUrls)
            {
                if (cancellationToken.IsCancellationRequested)
                    return;

                await eventDriver.Navigate().GoToUrlAsync(scheduleUrl).ConfigureAwait(false);
                eventDriver.FindElement(By.XPath("""//button[contains(@class, "schedule-list__load_more__button")]""")).Click();

                await Task.Delay(1_000, cancellationToken).ConfigureAwait(false);

                // TODO: validate groups of 3
                foreach (IWebElement boxScoreRowElement in eventDriver.FindElements(By.XPath(
                    """
                    //table//tr
                        [td
                            [contains(@class, "schedule-event-cell--firstTeam")]
                            [.//text()
                                [normalize-space() = "Alabama"
                                    or normalize-space() = "Arkansas"
                                    or normalize-space() = "Auburn"
                                    or normalize-space() = "Florida"
                                    or normalize-space() = "Georgia"
                                    or normalize-space() = "Kentucky"
                                    or normalize-space() = "LSU"
                                    or normalize-space() = "Ole Miss"
                                    or normalize-space() = "Mississippi State"
                                    or normalize-space() = "Missouri"
                                    or normalize-space() = "Oklahoma"
                                    or normalize-space() = "South Carolina"
                                    or normalize-space() = "Tennessee"
                                    or normalize-space() = "Texas"
                                    or normalize-space() = "Texas A&M"
                                    or normalize-space() = "Vanderbilt"
                                ]
                            ]
                        ]
                        [td
                            [contains(@class, "schedule-event-cell--secondTeam")]
                            [.//text()
                                [normalize-space() = "Alabama"
                                    or normalize-space() = "Arkansas"
                                    or normalize-space() = "Auburn"
                                    or normalize-space() = "Florida"
                                    or normalize-space() = "Georgia"
                                    or normalize-space() = "Kentucky"
                                    or normalize-space() = "LSU"
                                    or normalize-space() = "Ole Miss"
                                    or normalize-space() = "Mississippi State"
                                    or normalize-space() = "Missouri"
                                    or normalize-space() = "Oklahoma"
                                    or normalize-space() = "South Carolina"
                                    or normalize-space() = "Tennessee"
                                    or normalize-space() = "Texas"
                                    or normalize-space() = "Texas A&M"
                                    or normalize-space() = "Vanderbilt"
                                ]
                            ]
                        ]
                    """ +
                        //[td
                        //    [contains(@class, "schedule-event-cell--results_time")]
                        //    [.//text()
                        //        [contains(., "Thu.")
                        //            or contains(., "Fri.")
                        //            or contains(., "Sat.")
                        //            or contains(., "Sun.")
                        //        ]
                        //    ]
                        //]
                    """
                        [td
                            [contains(@class, "schedule-event-cell--schedule_event_links")]
                            [.//a[normalize-space() = "Box Score"]]
                        ]
                    """)))
                {
                    IWebElement boxScoreDateElement = boxScoreRowElement.FindElement(By.XPath("""td[contains(@class, "schedule-event-cell--results_time")]//span[not(@class)]"""));
                    DateOnly boxScoreDate = DateOnly.Parse(boxScoreDateElement.Text);

                    // TODO: appsettings.json
                    if (boxScoreDate < new DateOnly(DateTime.Now.Year, 5, 20) || boxScoreDate > new DateOnly(DateTime.Now.Year, 5, 25))
                        continue;

                    IWebElement boxScoreElement = boxScoreRowElement.FindElement(By.XPath("""td[contains(@class, "schedule-event-cell--schedule_event_links")]//a[normalize-space() = "Box Score"]"""));
                    boxScoreUrls.Add(new(secUrl, $"boxscore/iframe/{boxScoreElement.GetDomAttribute("href")!.Split('/', '\\')[^1]}"));
                }
            }

            logger.LogInformation("Removing duplicate box score URLs");

            // TODO: do this better
            //int gameNumber = 1;

            // TODO: log urls
            foreach (Uri boxScoreUrl in boxScoreUrls.Distinct())
            {
                if (cancellationToken.IsCancellationRequested)
                    return;

                await eventDriver.Navigate().GoToUrlAsync(boxScoreUrl).ConfigureAwait(false);

                IWebElement boxScoreIFrameElement = eventDriver.FindElement(By.XPath("""//iframe[@id = "boxscore"]"""));
                driver.SwitchTo().Frame(boxScoreIFrameElement);

                foreach (IWebElement hittingTableElement in eventDriver.FindElements(By.XPath("""//*[.//text()[normalize-space() = "Hitting"]]/following-sibling::*[1]//table""")))
                {
                    if (cancellationToken.IsCancellationRequested)
                        return;

                    ReadOnlyCollection<IWebElement> hitterElements = hittingTableElement.FindElements(By.XPath("""tbody/tr[td[1]//text() != "P"]"""));

                    IWebElement gameDateElement = eventDriver.FindElement(By.XPath("""//time"""));
                    string series = DateOnly.Parse(gameDateElement.Text) switch
                    {
                        var date when date >= new DateOnly(DateTime.Now.Year, 3, 14) && date <= new DateOnly(DateTime.Now.Year, 3, 16) => "1",
                        var date when date >= new DateOnly(DateTime.Now.Year, 3, 20) && date <= new DateOnly(DateTime.Now.Year, 3, 23) => "2",
                        var date when date >= new DateOnly(DateTime.Now.Year, 3, 27) && date <= new DateOnly(DateTime.Now.Year, 3, 30) => "3",
                        var date when date >= new DateOnly(DateTime.Now.Year, 4, 3) && date <= new DateOnly(DateTime.Now.Year, 4, 6) => "4",
                        var date when date >= new DateOnly(DateTime.Now.Year, 4, 10) && date <= new DateOnly(DateTime.Now.Year, 4, 13) => "5",
                        var date when date >= new DateOnly(DateTime.Now.Year, 4, 17) && date <= new DateOnly(DateTime.Now.Year, 4, 20) => "6",
                        var date when date >= new DateOnly(DateTime.Now.Year, 4, 24) && date <= new DateOnly(DateTime.Now.Year, 4, 27) => "7",
                        var date when date >= new DateOnly(DateTime.Now.Year, 5, 1) && date <= new DateOnly(DateTime.Now.Year, 5, 4) => "8",
                        var date when date >= new DateOnly(DateTime.Now.Year, 5, 8) && date <= new DateOnly(DateTime.Now.Year, 5, 11) => "9",
                        var date when date >= new DateOnly(DateTime.Now.Year, 5, 15) && date <= new DateOnly(DateTime.Now.Year, 5, 18) => "10",
                        var date when date >= new DateOnly(DateTime.Now.Year, 5, 20) && date <= new DateOnly(DateTime.Now.Year, 5, 25) => "SEC Tournament",
                        _ => throw new InvalidOperationException("Invalid series")
                    };

                    string gameNumber = DateOnly.Parse(gameDateElement.Text).ToString("dddd");

                    // TODO: stop inlining
                    ValueRange body = new()
                    {
                        Values =
                        [
                            [.. Enumerable.Repeat(eventDriver.FindElement(By.XPath("""//h2""")).Text.Replace(Environment.NewLine, " "), hitterElements.Count)],
                            [.. Enumerable.Repeat(gameDateElement.Text, hitterElements.Count)],
                            [.. Enumerable.Repeat(hittingTableElement.FindElement(By.XPath("""thead/tr[1]/th[last()]""")).Text, hitterElements.Count)],
                            [.. hitterElements.Select(hitter => hitter.FindElements(By.XPath("""td[2]""")) is { Count: > 0 } data ? data[0].Text : string.Empty)],
                            [.. hitterElements.Select(hitter => $"{(hitter.FindElements(By.XPath("""td[2]""")) is { Count: > 0 } data ? data[0].Text : string.Empty)}{series}{gameNumber}")],
                            [.. hitterElements.Select(hitter => hitter.FindElements(By.XPath("""td[3]""")) is { Count: > 0 } data ? data[0].Text : string.Empty)],
                            [.. Enumerable.Repeat(series, hitterElements.Count)],
                            [.. Enumerable.Repeat(gameNumber, hitterElements.Count)]
                        ],
                        MajorDimension = GoogleUtilities.GetEnumStringValue(GetRequest.MajorDimensionEnum.COLUMNS)
                    };

                    AppendRequest appendRequest = sheets.Spreadsheets.Values.Append(body, options.Value.Google.SpreadsheetId, $"{options.Value.Google.HittingSheetName}!A2");
                    appendRequest.ValueInputOption = AppendRequest.ValueInputOptionEnum.USERENTERED;
                    appendRequest.InsertDataOption = AppendRequest.InsertDataOptionEnum.OVERWRITE;

                    logger.LogInformation("Updating sheet {SheetName}", options.Value.Google.HittingSheetName);
                    _ = await appendRequest.ExecuteAsync(cancellationToken).ConfigureAwait(false);

                    await Task.Delay(1_000, cancellationToken).ConfigureAwait(false);
                }

                foreach (IWebElement pitchingTableElement in eventDriver.FindElements(By.XPath("""//*[.//text()[normalize-space() = "Pitching"]]/following-sibling::*[1]//table""")))
                {
                    if (cancellationToken.IsCancellationRequested)
                        return;

                    ReadOnlyCollection<IWebElement> pitcherElements = pitchingTableElement.FindElements(By.XPath("""tbody/tr"""));

                    IWebElement gameDateElement = eventDriver.FindElement(By.XPath("""//time"""));
                    string series = DateOnly.Parse(gameDateElement.Text) switch
                    {
                        var date when date >= new DateOnly(DateTime.Now.Year, 3, 14) && date <= new DateOnly(DateTime.Now.Year, 3, 16) => "1",
                        var date when date >= new DateOnly(DateTime.Now.Year, 3, 20) && date <= new DateOnly(DateTime.Now.Year, 3, 23) => "2",
                        var date when date >= new DateOnly(DateTime.Now.Year, 3, 27) && date <= new DateOnly(DateTime.Now.Year, 3, 30) => "3",
                        var date when date >= new DateOnly(DateTime.Now.Year, 4, 3) && date <= new DateOnly(DateTime.Now.Year, 4, 6) => "4",
                        var date when date >= new DateOnly(DateTime.Now.Year, 4, 10) && date <= new DateOnly(DateTime.Now.Year, 4, 13) => "5",
                        var date when date >= new DateOnly(DateTime.Now.Year, 4, 17) && date <= new DateOnly(DateTime.Now.Year, 4, 20) => "6",
                        var date when date >= new DateOnly(DateTime.Now.Year, 4, 24) && date <= new DateOnly(DateTime.Now.Year, 4, 27) => "7",
                        var date when date >= new DateOnly(DateTime.Now.Year, 5, 1) && date <= new DateOnly(DateTime.Now.Year, 5, 4) => "8",
                        var date when date >= new DateOnly(DateTime.Now.Year, 5, 8) && date <= new DateOnly(DateTime.Now.Year, 5, 11) => "9",
                        var date when date >= new DateOnly(DateTime.Now.Year, 5, 15) && date <= new DateOnly(DateTime.Now.Year, 5, 18) => "10",
                        var date when date >= new DateOnly(DateTime.Now.Year, 5, 20) && date <= new DateOnly(DateTime.Now.Year, 5, 25) => "SEC Tournament",
                        _ => throw new InvalidOperationException("Invalid series")
                    };

                    string gameNumber = DateOnly.Parse(gameDateElement.Text).ToString("dddd");

                    // TODO: stop inlining
                    ValueRange body = new()
                    {
                        Values =
                        [
                            [.. Enumerable.Repeat(eventDriver.FindElement(By.XPath("""//h2""")).Text.Replace(Environment.NewLine, " "), pitcherElements.Count)],
                            [.. Enumerable.Repeat(gameDateElement.Text, pitcherElements.Count)],
                            [.. Enumerable.Repeat(pitchingTableElement.FindElement(By.XPath("""thead/tr[1]/th[last()]""")).Text, pitcherElements.Count)],
                            [.. pitcherElements.Select(pitcher => Regex.Replace(pitcher.FindElements(By.XPath("""td[1]""")) is { Count: > 0 } data ? data[0].Text : string.Empty, @" *\([^)]*\)", string.Empty))],
                            [.. pitcherElements.Select(pitcher => $"{Regex.Replace(pitcher.FindElements(By.XPath("""td[1]""")) is { Count: > 0 } data ? data[0].Text : string.Empty, @" *\([^)]*\)", string.Empty)}{series}{gameNumber}")],
                            [.. pitcherElements.Select(pitcher => pitcher.FindElements(By.XPath("""td[2]""")) is { Count: > 0 } data ? data[0].Text : string.Empty)],
                            [.. pitcherElements.Select(pitcher => pitcher.FindElements(By.XPath("""td[13]""")) is { Count: > 0 } data ? data[0].Text : string.Empty)],
                            [.. pitcherElements.Select(pitcher => pitcher.FindElements(By.XPath("""td[16]""")) is { Count: > 0 } data ? data[0].Text : string.Empty)],
                            [.. Enumerable.Repeat(series, pitcherElements.Count)],
                            [.. Enumerable.Repeat(gameNumber, pitcherElements.Count)]
                        ],
                        MajorDimension = GoogleUtilities.GetEnumStringValue(GetRequest.MajorDimensionEnum.COLUMNS)
                    };

                    AppendRequest appendRequest = sheets.Spreadsheets.Values.Append(body, options.Value.Google.SpreadsheetId, $"{options.Value.Google.PitchingSheetName}!A2");
                    appendRequest.ValueInputOption = AppendRequest.ValueInputOptionEnum.USERENTERED;
                    appendRequest.InsertDataOption = AppendRequest.InsertDataOptionEnum.OVERWRITE;

                    logger.LogInformation("Updating sheet {SheetName}", options.Value.Google.PitchingSheetName);
                    _ = await appendRequest.ExecuteAsync(cancellationToken).ConfigureAwait(false);

                    await Task.Delay(1_000, cancellationToken).ConfigureAwait(false);
                }

                //gameNumber = (gameNumber % 3) + 1;
            }

            logger.LogInformation("Successfully finished populating spreadsheet");
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "An unhandled exception occurred");
            eventDriver.Quit(); // FIXME: shouldn't this be done automatically?
        }
    }
}