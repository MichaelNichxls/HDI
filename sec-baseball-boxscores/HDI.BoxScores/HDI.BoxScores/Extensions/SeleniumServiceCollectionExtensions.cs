using HDI.BoxScores.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using OpenQA.Selenium;
using OpenQA.Selenium.Chrome;
using System;

namespace HDI.BoxScores.Extensions;

public static class SeleniumServiceCollectionExtensions
{
    // TODO: scoped
    public static IServiceCollection AddChromeDriver(this IServiceCollection services) =>
        services.AddSingleton<IWebDriver, ChromeDriver>(
            static provider =>
            {
                var options = provider.GetRequiredService<IOptions<BoxScoreOptions>>();

                ChromeOptions chromeOptions = new();

                if (options.Value.Selenium.PageLoadStrategy is { } pageLoadStrategy)
                    chromeOptions.PageLoadStrategy = pageLoadStrategy;

                if (options.Value.Selenium.PageLoadTimeoutSeconds is { } pageLoadTimeoutSeconds)
                    chromeOptions.PageLoadTimeout = TimeSpan.FromSeconds(pageLoadTimeoutSeconds);

                if (options.Value.Selenium.ImplicitWaitTimeoutSeconds is { } implicitWaitTimeoutSeconds)
                    chromeOptions.ImplicitWaitTimeout = TimeSpan.FromSeconds(implicitWaitTimeoutSeconds);

                if (options.Value.Selenium.Arguments is { } arguments)
                    chromeOptions.AddArguments(arguments);

                if (options.Value.Selenium.ExcludedArguments is { } excludedArguments)
                    chromeOptions.AddExcludedArguments(excludedArguments);

                return options.Value.Selenium.HttpCommandTimeoutSeconds is { } httpCommandTimeoutSeconds
                    ? new(
                        ChromeDriverService.CreateDefaultService(),
                        chromeOptions,
                        TimeSpan.FromSeconds(httpCommandTimeoutSeconds))
                    : new(chromeOptions);
            });
}