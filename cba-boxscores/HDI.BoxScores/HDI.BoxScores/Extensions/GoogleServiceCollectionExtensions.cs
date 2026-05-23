using Google.Apis.Auth.OAuth2;
using Google.Apis.Services;
using Google.Apis.Sheets.v4;
using HDI.BoxScores.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;

namespace HDI.BoxScores.Extensions;

public static class GoogleServiceCollectionExtensions
{
    public static IServiceCollection AddSheetsService(this IServiceCollection services) =>
        services.AddSingleton<SheetsService>(
            static provider =>
            {
                var options = provider.GetRequiredService<IOptions<BoxScoreOptions>>();

                ICredential credential = GoogleCredential
                    .FromFile(options.Value.Google.CredentialFile)
                    .CreateScoped(SheetsService.Scope.Spreadsheets);

                BaseClientService.Initializer initializer = new()
                {
                    ApplicationName = options.Value.Google.ApplicationName,
                    HttpClientInitializer = credential
                };

                return new(initializer);
            });
}